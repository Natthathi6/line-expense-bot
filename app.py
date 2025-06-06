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
    month_prefix = today.strftime('%Y-%m')

    if msg.lower().strip() == "export":
        export_url = "https://line-expense-bot.onrender.com/export"
        reply_text(reply_token, f"📁 ดาวน์โหลดข้อมูล:
{export_url}")
        return "export link sent", 200

    if msg.lower().strip().startswith("del income "):
        try:
            input_date = msg.strip()[11:]
            db_date = datetime.strptime(input_date, "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type='income'", (user_id, db_date))
            conn.commit()
            reply_text(reply_token, f"🩹 ลบรายได้วันที่ {input_date} แล้ว")
            return "income deleted", 200
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ไม่ถูกต้อง เช่น: del income 02-06-2025")
            return "invalid date", 200

    if msg.lower().strip() == "weekly รายจ่าย":
        df = pd.read_sql_query("SELECT * FROM records WHERE type='expense'", conn)
        df["date"] = pd.to_datetime(df["date"])
        latest_month = df["date"].dt.to_period("M").max()
        df = df[df["date"].dt.to_period("M") == latest_month]
        df["week"] = df["date"].dt.day.apply(lambda d: f"Week {((d - 1) // 7) + 1}")

        df_user = df[df["user_id"] == user_id]
        if df_user.empty:
            reply_text(reply_token, "📍 ยังไม่มีรายจ่ายในเดือนนี้")
            return "no data", 200

        summary = df_user.groupby("week")["amount"].sum()
        total = df_user["amount"].sum()
        month_label = df_user["date"].dt.strftime("%B %Y").iloc[0]
        name = get_user_name(user_id)

        lines = [f"📊 รายจ่ายเดือน {month_label} ของ {name}"]
        for week in ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5"]:
            baht = summary.get(week, 0)
            lines.append(f"• {week}: {baht:,.0f} บาท")
        lines.append(f"\n💰 รวมทั้งเดือน: {total:,.0f} บาท")

        reply_text(reply_token, "\n".join(lines))
        return "weekly summary", 200

    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.rsplit(" ", 3)
            if len(parts) == 4:
                item, amount, category, dtype = parts
            elif len(parts) == 3:
                item, amount, dtype = parts
                category = "-"
            else:
                continue
            dtype = dtype.lower()
            if dtype not in ["รายจ่าย", "รายได้"]:
                continue
            amount = float(amount)
            records.append((user_id, item, amount, category, "expense" if dtype == "รายจ่าย" else "income", today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: ค่าน้ำ 120 ของใช้ รายจ่าย")
        return "bad format", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()

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
