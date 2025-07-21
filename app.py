import time
import json
import requests
from flask import Flask, jsonify, send_from_directory
import threading
import os
import concurrent.futures

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

app = Flask(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))
usernames_file = os.path.join(dir_path, 'usernames.txt')

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

MAX_WORKERS = 10  # Concurrency level
available_usernames = []

# --- Telegram notifier ---
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"[!] Telegram failed: {r.text}")
    except Exception as e:
        print(f"[!] Telegram exception: {e}")

# --- Check username ---
def check_username(username):
    data = {"username": username}
    try:
        resp = requests.post(CHECK_URL, headers=HEADERS, json=data)
        if resp.status_code == 200:
            return not resp.json().get("taken", True)
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            print(f"[!] Rate limit: sleeping {retry_after}s...")
            time.sleep(retry_after)
            return check_username(username)
        else:
            print(f"[!] Error: {resp.status_code} for {username}")
            return False
    except Exception as e:
        print(f"[!] Exception checking {username}: {e}")
        return False

# --- Load usernames ---
def load_usernames():
    if not os.path.exists(usernames_file):
        print(f"[!] '{usernames_file}' not found.")
        return []
    with open(usernames_file, 'r') as f:
        return [line.strip() for line in f if line.strip()]

# --- Task for pool ---
def username_check_task(username):
    if check_username(username):
        print(f"[+] Available: {username}")
        send_telegram(f"✅ Available username found: {username}")
        return username
    else:
        print(f"[-] Taken: {username}")
        return None

# --- Background checker ---
def username_checker_loop():
    global available_usernames
    send_telegram("🚀 Username checker started!")
    available_usernames = []

    usernames = load_usernames()
    if not usernames:
        send_telegram("⚠️ No usernames found.")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(username_check_task, u) for u in usernames]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                available_usernames.append(result)

    report = "📋 Check complete.\n"
    if available_usernames:
        report += "Available:\n" + "\n".join(available_usernames)
    else:
        report += "No usernames available."
    send_telegram(report)
    send_telegram("🛑 Checker stopped.")

# --- Start thread ---
def start_check_thread():
    thread = threading.Thread(target=username_checker_loop)
    thread.daemon = True
    thread.start()

# --- Telegram commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bot is running. Use /redeploy to restart the Render service.")

async def redeploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return
    if not RENDER_DEPLOY_HOOK_URL:
        await update.message.reply_text("⚠️ No deploy hook URL.")
        return
    try:
        r = requests.post(RENDER_DEPLOY_HOOK_URL)
        if r.status_code == 200:
            await update.message.reply_text("✅ Deploy triggered.")
        else:
            await update.message.reply_text(f"❌ Failed: {r.status_code}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

def run_telegram_bot():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured. Skipping bot.")
        return
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("redeploy", redeploy))
    threading.Thread(target=application.run_polling, daemon=True).start()

# --- Flask Routes ---
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/available_usernames')
def get_available_usernames():
    return jsonify(available_usernames)

# --- Main ---
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not set.")
        exit(1)

    run_telegram_bot()
    start_check_thread()

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
