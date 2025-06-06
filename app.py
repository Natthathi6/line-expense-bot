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
        export_url = "https://line-expense-bot.onrender.com/export"
        reply_text(reply_token, f"📁 ดาวน์โหลดข้อมูล:\n{export_url}")
        return "export", 200

    # --- CUSTOM RANGE INCOME ---
    if msg.lower().startswith("รายได้รวม"):
        try:
            text = msg.strip()[10:].replace(" ", "")
            range_part = text.split("รายได้")[0].strip()
            d1, d2 = range_part.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records WHERE type='income'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]

            if df.empty:
                reply_text(reply_token, "📍 ไม่มีรายได้ในช่วงที่ระบุ")
                return "no income", 200

            total = df["amount"].sum()
            by_cat = df.groupby("category")["amount"].sum()
            by_item = df.groupby("item")["amount"].sum()

            icons = {
                "อาหาร": "🍟",
                "เครื่องดื่ม": "🍺",
                "โอน": "📌",
                "เงินสด": "📌",
                "เครดิต": "📌"
            }

            lines = [f"💵 รายได้ {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')}"]
            if "รวม" in by_cat:
                lines.append(f"💵 รายได้รวม: {by_cat['รวม']:,.0f} บาท")
            for key in ["อาหาร", "เครื่องดื่ม"]:
                if key in by_cat:
                    lines.append(f"{icons.get(key, '')} รายได้{key}: {by_cat[key]:,.0f} บาท")

            lines.append("")
            for key in ["โอน", "เงินสด", "เครดิต"]:
                if key in by_item:
                    lines.append(f"{icons.get(key, '')} {key}: {by_item[key]:,.0f} บาท")

            lines.append(f"\n💰 รวม: {total:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "income summary", 200
        except Exception as e:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายได้รวม 1-6/06/2025")
            return "parse error", 200

    # --- INSERT RECORDS ---
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, last = parts
                amount = float(amount)
                if last == "รายได้":
                    dtype = "income"
                    category = item.replace("รายได้", "").strip() or "-"
                else:
                    dtype = "expense"
                    category = last
                records.append((user_id, item.strip(), amount, category, dtype, today_str))
            elif len(parts) == 2:
                item, amount = parts
                amount = float(amount)
                records.append((user_id, item.strip(), amount, "-", "expense", today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: ค่าข้าว 50 อาหาร หรือ รายได้รวม 10000 รายได้")
        return "bad format", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    conn.close()

    reply_text(reply_token, f"✅ บันทึกรายการแล้ว {len(records)} รายการ")
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
