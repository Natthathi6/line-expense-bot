from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
import requests
from openpyxl import Workbook

app = Flask(__name__)
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")

user_map = {
    "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
    "U8a82b2393123c38a238144698e8fd19b": "Pupae"
}

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
                  headers=headers, json=payload)

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

    conn = sqlite3.connect("expenses.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses
                    (user_id TEXT, item TEXT, amount REAL, date TEXT)""")

    today = datetime.now().strftime('%Y-%m-%d')
    today_display = datetime.now().strftime('%d-%m-%Y')
    month_prefix = datetime.now().strftime('%Y-%m')

    # export
    if msg.lower().strip() == "export":
        export_url = "https://line-expense-bot.onrender.com/export"
        reply_text(reply_token, f"📁 ดาวน์โหลดรายจ่าย:\n{export_url}")
        return "sent export link", 200

    # clear all
    if msg.lower().strip() == "clear":
        conn.execute("DELETE FROM expenses WHERE user_id=?", (user_id,))
        conn.commit()
        reply_text(reply_token, "🧹 เคลียร์รายจ่ายทั้งหมดเรียบร้อยแล้ว")
        return "cleared all", 200

    # clear 02-06-2025
    if msg.lower().startswith("clear "):
        try:
            input_date = msg[6:].strip()
            date_obj = datetime.strptime(input_date, "%d-%m-%Y")
            db_date = date_obj.strftime("%Y-%m-%d")
            conn.execute("DELETE FROM expenses WHERE user_id=? AND date=?", (user_id, db_date))
            conn.commit()
            reply_text(reply_token, f"🧹 ลบรายจ่ายวันที่ {input_date} แล้ว")
            return "cleared specific date", 200
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ไม่ถูกต้อง เช่น: clear 02-06-2025")
            return "invalid clear date", 200

    # add expense
    try:
        item, amount = msg.rsplit(" ", 1)
        amount = float(amount)
    except:
        reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: กาแฟ 50")
        return "format error", 200

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
    lines = [f"📅 รายจ่ายวันนี้ ({today_display})"]
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
    ws.append(["User", "Item", "Amount", "Date"])
    for user_id, item, amount, date in rows:
        user = user_map.get(user_id, user_id)
        show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        ws.append([user, item, amount, show_date])

    file_path = "expenses_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
