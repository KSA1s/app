import os
import time
import requests
import threading
import concurrent.futures
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

app = Flask(__name__)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RENDER_DEPLOY_HOOK_URL = os.getenv("RENDER_DEPLOY_HOOK_URL")

CHECK_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://discord.com",
    "Authorization": DISCORD_TOKEN,
}

MAX_WORKERS = 10
available_usernames = []
usernames_file = "usernames.txt"


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured properly.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"[!] Telegram send failed: {r.text}")
    except Exception as e:
        print(f"[!] Telegram error: {e}")


def check_username(username):
    data = {"username": username}
    try:
        resp = requests.post(CHECK_URL, headers=HEADERS, json=data)
        if resp.status_code == 200:
            result = resp.json()
            return not result.get("taken", True)
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            print(f"Rate limited, sleeping {retry_after}s...")
            time.sleep(retry_after)
            return check_username(username)
        else:
            print(f"Error checking {username}: {resp.text}")
            return False
    except Exception as e:
        print(f"Exception checking {username}: {e}")
        return False


def load_usernames():
    if not os.path.exists(usernames_file):
        print(f"[!] {usernames_file} not found.")
        return []
    with open(usernames_file, "r") as f:
        return [line.strip() for line in f if line.strip()]


def username_check_task(username):
    if check_username(username):
        print(f"[+] Available: {username}")
        send_telegram(f"✅ Available username found: {username}")
        return username
    else:
        print(f"[-] Taken: {username}")
        return None


def username_checker_loop():
    global available_usernames
    send_telegram("🚀 Username checker started!")
    available_usernames = []

    usernames = load_usernames()
    if not usernames:
        send_telegram("⚠️ No usernames to check.")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(username_check_task, u): u for u in usernames}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                available_usernames.append(result)

    report = (
        "📋 Username check completed.\n"
        + ("Available usernames:\n" + "\n".join(available_usernames) if available_usernames else "No available usernames found.")
    )
    send_telegram(report)
    send_telegram("🛑 Username checker stopped.")


def start_check_thread():
    thread = threading.Thread(target=username_checker_loop)
    thread.daemon = True
    thread.start()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = f"Hi, {user.first_name}! This bot is working."
    await update.message.reply_text(msg)
    send_telegram(f"User {user.username or user.id} started the bot.")


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
        print("[!] Telegram environment variables missing, skipping bot start.")
        return
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("redeploy", redeploy))
    threading.Thread(target=application.run_polling, daemon=True).start()


@app.route("/available_usernames")
def available_usernames_route():
    global available_usernames
    return jsonify(available_usernames)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("[!] DISCORD_TOKEN environment variable required!")
        exit(1)

    run_telegram_bot()
    start_check_thread()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
