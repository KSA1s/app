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

MAX_WORKERS = 10  # Number of threads to check usernames concurrently
available_usernames = []

# --- Telegram notification function ---
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured. Skipping notification.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": str(TELEGRAM_CHAT_ID), "text": msg}
        print(f"[DEBUG] Sending Telegram message: {msg}")
        r = requests.post(url, data=payload)
        print(f"[DEBUG] Telegram response status: {r.status_code}, body: {r.text}")
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

# --- Worker task for ThreadPool ---
def username_check_task(username):
    if check_username(username):
        print(f"[+] Available: {username}")
        send_telegram(f"✅ Available username found: {username}")
        return username
    else:
        print(f"[-] Taken: {username}")
        return None

# --- Background checker thread with concurrency ---
def username_checker_loop():
    global available_usernames

    send_telegram("🚀 Username checker started!")
    available_usernames = []

    usernames = load_usernames()
    if not usernames:
        send_telegram("⚠️ No usernames found to check.")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(username_check_task, username): username for username in usernames}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                available_usernames.append(result)

    if available_usernames:
        report = "📋 Username check completed.\nAvailable usernames:\n" + "\n".join(available_usernames)
    else:
        report = "📋 Username check completed.\nNo available usernames found."

    send_telegram(report)
    send_telegram("🛑 Username checker stopped.")

# --- Start checking in background ---
def start_check_thread():
    thread = threa
