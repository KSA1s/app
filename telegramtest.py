import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Set your bot token and chat id here or via environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "847352696"  # your chat id as string

def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }
    try:
        resp = requests.post(url, data=payload)
        if resp.status_code != 200:
            print(f"[!] Telegram send failed: {resp.status_code} {resp.text}")
        else:
            print(f"[+] Telegram message sent: {msg}")
    except Exception as e:
        print(f"[!] Telegram exception: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! This bot is working.")
    # Also send message to your chat id to confirm send_telegram works
    send_telegram(f"User {update.message.from_user.username} started the bot.")

def main():
    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Please set your TELEGRAM_BOT_TOKEN before running.")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
