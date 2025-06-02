from flask import Flask, request
import os
import sqlite3
from datetime import datetime
import requests

app = Flask(__name__)
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")

def reply_text(reply_token, text):
    headers = {
        'Authorization': f'Bearer {LINE_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': text
        }]
    }
    requests.post('https://api.line.me/v2/bot/message/reply',
                  headers=headers,
                  json=payload)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        msg = data["events"][0]["message"]["text"]
        user_id = data["events"][0]["source"]["userId"]
        reply_token = data["events"][0]["replyToken"]
    except:
        return "ignored", 200

    # เตรียมเชื่อมต่อฐานข้อมูล
    conn = sqlite3.connect("expenses.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses
                    (user_id TEXT, item TEXT, amount REAL, date TEXT)""")

    today = datetime.now().strftime('%Y-%m-%d')
    month_prefix = datetime.now().strftime('%Y-%m')

    success_count = 0
    lines = msg.strip().split("\n")
    for line in lines:
        try:
            item, amount = line.rsplit(" ", 1)
            amount = float(amount)
            conn.execute("INSERT INTO expenses VALUES (?, ?, ?, ?)",
                         (user_id, item.strip(), amount, today))
            success_count += 1
        except:
            pass  # ข้ามบรรทัดที่พิมพ์ผิด

    conn.commit()

    rows = conn.execute(
        "SELECT item, amount FROM expenses WHERE user_id=? AND date=?",
        (user_id, today)).fetchall()

    month_total = conn.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date LIKE ?",
        (user_id, f"{month_prefix}-%")).fetchone()[0] or 0

    conn.close()

    total_today = sum(r[1] for r in rows)
    response_lines = [f"📅 รายจ่ายวันนี้ ({today})"]
    for r in rows:
        response_lines.append(f"- {r[0]}: {r[1]:,.0f} บาท")
    response_lines.append(f"💸 รวมวันนี้: {total_today:,.0f} บาท")
    response_lines.append(f"🗓 รวมเดือนนี้: {month_total:,.0f} บาท")

    reply_text(reply_token, "\n".join(response_lines))
    return "OK", 200

@app.route("/")
def index():
    return "<h2>✅ LINE Expense Bot is running!</h2>"
