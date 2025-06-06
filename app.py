from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
import requests
from openpyxl import Workbook
import pandas as pd

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
        'messages': [{'type': 'text', 'text': text}]
    }
    requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=payload)

@app.route("/")
def index():
    return "✅ LINE Bot is running!"

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
        reply_text(reply_token, f"\U0001F4C1 ดาวน์โหลดข้อมูล:\n{export_url}")
        return "export link sent", 200

    if msg.lower().strip() == "weekly รายจ่าย":
        df = pd.read_sql_query("SELECT * FROM records WHERE type='expense'", conn)
        if df.empty:
            reply_text(reply_token, "📍 ยังไม่มีรายจ่ายในระบบ")
            return "no data", 200

        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"].dt.to_period("M") == df["date"].dt.to_period("M").max()]
        df["week"] = df["date"].dt.day.apply(lambda d: f"Week {((d - 1) // 7) + 1}")
        df_user = df[df["user_id"] == user_id]
        if df_user.empty:
            reply_text(reply_token, "📍 ยังไม่มีรายจ่ายของคุณในเดือนนี้")
            return "no data", 200

        summary = df_user.groupby("week")["amount"].sum()
        total = df_user["amount"].sum()
        lines = [f"📊 รายจ่ายของคุณในเดือน {df_user['date'].dt.strftime('%B %Y').iloc[0]}"]
        for week in ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5"]:
            baht = summary.get(week, 0)
            lines.append(f"• {week}: {baht:,.0f} บาท")
        lines.append(f"\n💰 รวมทั้งเดือน: {total:,.0f} บาท")
        reply_text(reply_token, "\n".join(lines))
        return "weekly summary", 200

    # --- บันทึกรายรับ/รายจ่าย ---
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, t = parts
                category = "-"
            elif len(parts) == 4:
                item, amount, category, t = parts
            else:
                continue
            t = t.strip()
            dtype = "income" if t == "รายได้" else "expense"
            amount = float(amount)
            records.append((user_id, item.strip(), amount, category.strip(), dtype, today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รายได้รวม 13000 รายได้ หรือ ข้าว 50")
        return "invalid format", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    conn.close()

    income_sum = sum(r[2] for r in records if r[4] == "income")
    expense_sum = sum(r[2] for r in records if r[4] == "expense")
    response_lines = [f"📅 บันทึกวันที่ {today_display}"]
    if income_sum:
        response_lines.append(f"💵 รายได้รวม: {income_sum:,.0f} บาท")
    if expense_sum:
        response_lines.append(f"💸 รายจ่ายรวม: {expense_sum:,.0f} บาท")
    reply_text(reply_token, "\n".join(response_lines))
    return "OK", 200

@app.route("/export", methods=["GET"])
def export_excel():
    conn = sqlite3.connect("runtime.db")
    rows = conn.execute("SELECT * FROM records").fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Records"
    ws.append(["User", "Item", "Amount", "Category", "Type", "Date"])
    for r in rows:
        name = user_map.get(r[0], "คุณ")
        show_date = datetime.strptime(r[5], "%Y-%m-%d").strftime("%d-%m-%Y")
        ws.append([name, r[1], r[2], r[3], r[4], show_date])

    file_path = "records_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
