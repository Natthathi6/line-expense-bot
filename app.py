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

    # --- EXPORT ---
    if msg.lower().strip() == "export":
        rows = conn.execute("SELECT user_id, item, amount, category, type, date FROM records").fetchall()
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
        conn.close()
        return send_file(file_path, as_attachment=True)

    # --- PARSE RECORD ---
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, final = parts
                if final == "รายได้":
                    type_ = "income"
                    category = "-"
                else:
                    item, amount, category = parts
                    type_ = "expense"
            elif len(parts) == 2:
                item, amount = parts
                type_ = "expense"
                category = "-"
            else:
                continue
            amount = float(amount.replace(",", ""))
            records.append((user_id, item.strip(), amount, category.strip(), type_, today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: ข้าว 50 อาหาร หรือ รายได้รวม 10000 รายได้")
        return "invalid format", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    df = pd.DataFrame(records, columns=["user_id", "item", "amount", "category", "type", "date"])

    if all(r[4] == "income" for r in records):
        summary = {
            "รวม": 0,
            "อาหาร": 0,
            "เครื่องดื่ม": 0,
            "โอน": 0,
            "เงินสด": 0,
            "เครดิต": 0
        }
        for _, item, amount, _, _, _ in records:
            if "รวม" in item:
                summary["รวม"] += amount
            elif "อาหาร" in item:
                summary["อาหาร"] += amount
            elif "เครื่องดื่ม" in item:
                summary["เครื่องดื่ม"] += amount
            elif "โอน" in item:
                summary["โอน"] += amount
            elif "เงินสด" in item:
                summary["เงินสด"] += amount
            elif "เครดิต" in item:
                summary["เครดิต"] += amount

        def format_amt(amt):
            return f"{amt:,.0f}" if amt.is_integer() else f"{amt:,.2f}"

        reply = [
            f"📅 บันทึกวันที่ {today_display}",
            f"💵 รายได้รวม: {format_amt(summary['รวม'])} บาท",
            f"🍟 รายได้อาหาร: {format_amt(summary['อาหาร'])} บาท",
            f"🍺 รายได้เครื่องดื่ม: {format_amt(summary['เครื่องดื่ม'])} บาท",
            "",
            f"📌 โอน: {format_amt(summary['โอน'])} บาท",
            f"📌 เงินสด: {format_amt(summary['เงินสด'])} บาท",
            f"📌 เครดิต: {format_amt(summary['เครดิต'])} บาท"
        ]
        reply_text(reply_token, "\n".join(reply))
        return "OK", 200
    else:
        total = df["amount"].sum()
        reply = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for _, row in df.iterrows():
            if row["category"] != "-":
                reply.append(f"- {row['item']}: {row['amount']:.0f} บาท ({row['category']})")
            else:
                reply.append(f"- {row['item']}: {row['amount']:.0f} บาท")
        reply.append(f"\n💸 รวมวันนี้: {total:,.0f} บาท")
        reply_text(reply_token, "\n".join(reply))
        return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
