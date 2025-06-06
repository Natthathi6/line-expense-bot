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
            parts = line.strip().rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, tag = parts
                tag = tag.strip()
                if tag == "รายได้":
                    record_type = "income"
                    category = item.replace("รายได้", "").strip()
                    item = category if category else "ไม่ระบุ"
                else:
                    record_type = "expense"
                    category = tag
                amount = float(amount)
            elif len(parts) == 2:
                item, amount = parts
                amount = float(amount)
                record_type = "expense"
                category = "-"
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
    summary = df.groupby(["type", "category"])["amount"].sum()
    reply = [f"📅 รายการวันนี้ ({today_display})"]
    for (t, c), a in summary.items():
        label = "รายได้" if t == "income" else "รายจ่าย"
        reply.append(f"• {label}{f'({c})' if c != '-' else ''}: {a:,.0f} บาท")

    reply_text(reply_token, "\n".join(reply))
    return "OK", 200


@app.route("/export", methods=["GET"])
def export_excel():
    conn = sqlite3.connect("runtime.db")
    rows = conn.execute("SELECT user_id, item, amount, category, type, date FROM records").fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Records"
    ws.append(["User", "Item", "Amount", "Category", "Type", "Date"])
    for user_id, item, amount, category, dtype, date in rows:
        user = get_user_name(user_id)
        show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        ws.append([user, item, amount, category, dtype, show_date])

    file_path = "records_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
