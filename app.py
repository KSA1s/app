import time
import json
import requests
from flask import Flask, jsonify, send_from_directory
import threading
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

app = Flask(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))
usernames_file = os.path.join(dir_path, 'usernames.txt')
available_file = os.path.join(dir_path, 'available_usernames.txt')

CHECK_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"

# Read environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RENDER_DEPLOY_HOOK_URL = os.getenv("RENDER_DEPLOY_HOOK_URL")

HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://discord.com",
    "Authorization": DISCORD_TOKEN
}

DELAY = 2  # seconds between requests
available_usernames = []

# --- Telegram notification function ---
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured. Skipping notification.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"[!] Failed to send Telegram message: {r.text}")
    except Exception as e:
        print(f"[!] Telegram error: {e}")

# --- Check username availability ---
def check_username(username):
    data = {"username": username}
    try:
        resp = requests.post(CHECK_URL, headers=HEADERS, json=data)
        if resp.status_code == 200:
            result = resp.json()
            return result.get("taken") == False
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            print(f"Rate limited. Sleeping {retry_after} seconds...")
            time.sleep(retry_after)
            return check_username(username)
        else:
            print(f"Error checking {username}: {resp.text}")
            return False
    except Exception as e:
        print(f"Exception checking {username}: {e}")
        return False

# --- Load usernames from file ---
def load_usernames():
    if not os.path.exists(usernames_file):
        print(f"'{usernames_file}' not found. Please create it with usernames to check.")
        return []
    with open(usernames_file, 'r') as f:
        return [line.strip() for line in f if line.strip()]

# --- Save available username to file ---
def save_available(username):
    with open(available_file, 'a') as f:
        f.write(username + "\n")

# --- Background checker thread ---
def username_checker_loop():
    global available_usernames

    # Notify on Telegram if deploy hook URL exists (just once)
    if RENDER_DEPLOY_HOOK_URL:
        send_telegram(f"🔔 Deploy Hook URL detected: {RENDER_DEPLOY_HOOK_URL}")
    else:
        print("[!] No Deploy Hook URL set, skipping deploy notification.")

    usernames = load_usernames()
    available_usernames = []

    for username in usernames:
        if check_username(username):
            print(f"[+] Available: {username}")
            available_usernames.append(username)
            save_available(username)
            send_telegram(f"✅ Available username found: {username}")  # Telegram alert
        else:
            print(f"[-] Taken: {username}")
        time.sleep(DELAY)

# --- Start checking in background ---
def start_check_thread():
    thread = threading.Thread(target=username_checker_loop)
    thread.daemon = True
    thread.start()

# --- Telegram bot handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Use /redeploy to trigger a Render deploy.")

async def redeploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("🚫 You are not authorized to run this command.")
        return
    if not RENDER_DEPLOY_HOOK_URL:
        await update.message.reply_text("⚠️ Deploy hook URL not configured.")
        return
    try:
        resp = requests.post(RENDER_DEPLOY_HOOK_URL)
        if resp.status_code == 200:
            await update.message.reply_text("✅ Deploy triggered successfully!")
        else:
            await update.message.reply_text(f"❌ Deploy failed with status {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error triggering deploy: {e}")

def run_telegram_bot():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram bot environment variables missing, skipping bot startup.")
        return

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("redeploy", redeploy))

    # Run the bot asynchronously in a separate thread
    threading.Thread(target=application.run_polling, daemon=True).start()

# --- Flask Routes ---
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/available_usernames')
def get_available_usernames():
    global available_usernames
    return jsonify(available_usernames)

# --- Main Entry ---
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("❌ ERROR: Please set your DISCORD_TOKEN environment variable.")
        exit(1)

    run_telegram_bot()
    start_check_thread()

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
