from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
import requests
from openpyxl import Workbook
import pandas as pd

app = Flask(__name__)
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")

def get_user_name(user_id):
    return {
        "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
        "U8a82b2393123c38a238144698e8fd19b": "Pupae"
    }.get(user_id, "คุณ")

def reply_text(reply_token, text):
    headers = {
        'Authorization': f'Bearer {LINE_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'replyToken': reply_token,
        'messages': [{'type': 'text', 'text': text}]
    }
    requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=payload)

@app.route("/")
def index():
    return "✅ LINE Income/Expense Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        msg = data["events"][0]["message"]["text"]
        user_id = data["events"][0]["source"]["userId"]
        reply_token = data["events"][0]["replyToken"]
    except:
        return "ignored", 200

    conn = sqlite3.connect("runtime.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            user_id TEXT,
            item TEXT,
            amount REAL,
            category TEXT,
            type TEXT,
            date TEXT
        )
    """)

    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    today_display = today.strftime('%d-%m-%Y')

    # --- PARSE NEW RECORDS ---
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.strip().rsplit(" ", 3)
            if len(parts) == 4:
                item, amount, category, tag = parts
            elif len(parts) == 3:
                item, amount, tag = parts
                category = "-"
            elif len(parts) == 2:
                item, amount = parts
                category = "-"
                tag = "รายจ่าย"
            else:
                continue

            amount = float(amount)
            tag = tag.strip().lower()
            if tag == "รายได้":
                record_type = "income"
            elif tag == "รายจ่าย":
                record_type = "expense"
            else:
                continue
            records.append((user_id, item.strip(), amount, category.strip(), record_type, today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: ข้าว 50 อาหาร หรือ รายได้รวม 10000 รายได้")
        return "bad format", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    conn.close()

    df = pd.DataFrame(records, columns=["user_id", "item", "amount", "category", "type", "date"])
    reply_lines = [f"📅 บันทึกวันที่ {today_display}"]

    if not df[df["type"] == "expense"].empty:
        total_exp = df[df["type"] == "expense"]["amount"].sum()
        reply_lines.append(f"🧾 รายจ่ายรวม: {total_exp:,.0f} บาท")
    if not df[df["type"] == "income"].empty:
        total_inc = df[df["type"] == "income"]["amount"].sum()
        reply_lines.append(f"💵 รายได้รวม: {total_inc:,.0f} บาท")

    reply_text(reply_token, "\n".join(reply_lines))
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
