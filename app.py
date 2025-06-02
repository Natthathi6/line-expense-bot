from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
import requests
from openpyxl import Workbook

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
    return "✅ LINE Expense Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        msg = data["events"][0]["message"]["text"]
        user_id = data["events"][0]["source"]["userId"]
        reply_token = data["events"][0]["replyToken"]
    except:
        return "ignored", 200

    # พิมพ์ว่า export เพื่อขอลิงก์ดาวน์โหลด
    if msg.lower().strip() == "export":
        export_url = "https://line-expense-bot.onrender.com/export"
        reply_text(reply_token, f"📁 ดาวน์โหลดรายจ่าย:\n{export_url}")
        return "sent export link", 200

    # บันทึกรายจ่าย
    try:
        item, amount = msg.rsplit(" ", 1)
        amount = float(amount)
    except:
        reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: กาแฟ 50")
        return "format error", 200

    conn = sqlite3.connect("expenses.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses
                    (user_id TEXT, item TEXT, amount REAL, date TEXT)""")

    today = datetime.now().strftime('%Y-%m-%d')
    month_prefix = datetime.now().strftime('%Y-%m')

    conn.execute("INSERT INTO expenses VALUES (?, ?, ?, ?)",
                 (user_id, item, amount, today))
    conn.commit()

    rows = conn.execute(
        "SELECT item, amount FROM expenses WHERE user_id=? AND date=?",
        (user_id, today)).fetchall()

    month_total = conn.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date LIKE ?",
        (user_id, f"{month_prefix}-%")).fetchone()[0] or 0

    conn.close()

    total_today = sum(r[1] for r in rows)
    lines = [f"📅 รายจ่ายวันนี้ ({today})"]
    for r in rows:
        lines.append(f"- {r[0]}: {r[1]:,.0f} บาท")
    lines.append(f"💸 รวมวันนี้: {total_today:,.0f} บาท")
    lines.append(f"🗓 รวมเดือนนี้: {month_total:,.0f} บาท")

    reply_text(reply_token, "\n".join(lines))
    return "OK", 200

@app.route("/export", methods=["GET"])
def export_excel():
    conn = sqlite3.connect("expenses.db")
    rows = conn.execute("SELECT user_id, item, amount, date FROM expenses").fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["User ID", "Item", "Amount", "Date"])
    for row in rows:
        ws.append(row)

    file_path = "expenses_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
