from flask import Flask, request
import requests, sqlite3
from datetime import datetime
import os

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


@app.route("/")
def index():
    return "<h2>👋 LINE Expense Bot is running!</h2>"


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        msg = data["events"][0]["message"]["text"]
        user_id = data["events"][0]["source"]["userId"]
        reply_token = data["events"][0]["replyToken"]
    except:
        return "ignored", 200

    try:
        item, amount = msg.rsplit(' ', 1)
        amount = float(amount)
    except:
        reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: กาแฟ 50")
        return "format error", 200

    conn = sqlite3.connect("expenses.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses
                    (user_id TEXT, item TEXT, amount REAL, date TEXT)""")

    date_today = datetime.now().strftime('%Y-%m-%d')
    month_prefix = datetime.now().strftime('%Y-%m')

    # บันทึกรายการใหม่
    conn.execute("INSERT INTO expenses VALUES (?, ?, ?, ?)",
                 (user_id, item, amount, date_today))
    conn.commit()

    # ดึงข้อมูลรายวัน
    daily_rows = conn.execute(
        "SELECT item, amount FROM expenses WHERE user_id=? AND date=?",
        (user_id, date_today)).fetchall()

    # ดึงยอดรวมรายเดือน
    monthly_total = conn.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date LIKE ?",
        (user_id, f"{month_prefix}-%")).fetchone()[0] or 0

    conn.close()

    total_daily = sum([r[1] for r in daily_rows])
    lines = [f"📅 รายจ่ายวันนี้ ({datetime.now().strftime('%d/%m/%Y')})"]
    for r in daily_rows:
        lines.append(f"- {r[0]}: {r[1]:,.0f} บาท")
    lines.append(f"💸 รวมวันนี้: {total_daily:,.0f} บาท")
    lines.append(f"🗓 รวมเดือนนี้: {monthly_total:,.0f} บาท")

    reply_text(reply_token, '\n'.join(lines))
    return "OK", 200
