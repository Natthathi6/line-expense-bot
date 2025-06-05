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
        'messages': [{
            'type': 'text',
            'text': text
        }]
    }
    requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=payload)

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

    conn = sqlite3.connect("runtime.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses
                    (user_id TEXT, item TEXT, amount REAL, category TEXT, date TEXT)""")

    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    today_display = today.strftime('%d-%m-%Y')
    month_prefix = today.strftime('%Y-%m')

    if msg.lower().strip() == "export":
        export_url = "https://line-expense-bot.onrender.com/export"
        reply_text(reply_token, f"\U0001F4C1 ดาวน์โหลดรายจ่าย:\n{export_url}")
        return "sent export link", 200

    if msg.lower().strip() == "clear":
        conn.execute("DELETE FROM expenses WHERE user_id=?", (user_id,))
        conn.commit()
        reply_text(reply_token, "🧹 เคลียร์รายจ่ายทั้งหมดเรียบร้อยแล้ว")
        return "cleared all", 200

    if msg.lower().startswith("clear "):
        try:
            input_date = msg[6:].strip()
            db_date = datetime.strptime(input_date, "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM expenses WHERE user_id=? AND date=?", (user_id, db_date))
            conn.commit()
            reply_text(reply_token, f"🧹 ลบรายจ่ายวันที่ {input_date} แล้ว")
            return "cleared specific date", 200
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ไม่ถูกต้อง เช่น: clear 02-06-2025")
            return "invalid clear date", 200

    if msg.lower().strip() == "weekly":
        df = pd.read_sql_query("SELECT * FROM expenses", conn)
        if df.empty:
            reply_text(reply_token, "❌ ยังไม่มีข้อมูลรายจ่ายเลย")
            return "no data", 200

        df["date"] = pd.to_datetime(df["date"])
        latest_month = df["date"].dt.to_period("M").max()
        df = df[df["date"].dt.to_period("M") == latest_month]

        def classify_week(d):
            if d.day <= 7:
                return "Week 1 (1-7)"
            elif d.day <= 14:
                return "Week 2 (8-14)"
            elif d.day <= 21:
                return "Week 3 (15-21)"
            else:
                return "Week 4 (22-end)"

        df["week"] = df["date"].apply(classify_week)
        df_user = df[df["user_id"] == user_id]

        if df_user.empty:
            reply_text(reply_token, "❌ ยังไม่มีรายจ่ายของคุณในเดือนนี้เลย")
            return "no data user", 200

        summary = df_user.groupby("week")["amount"].sum()
        total = df_user["amount"].sum()
        latest_month_str = df_user["date"].dt.strftime("%B %Y").iloc[0]
        name = get_user_name(user_id)

        lines = [f"📊 รายจ่ายเดือน {latest_month_str} ของ {name}"]
        for week in ["Week 1 (1-7)", "Week 2 (8-14)", "Week 3 (15-21)", "Week 4 (22-end)"]:
            baht = summary.get(week, 0)
            lines.append(f"• {week}: {baht:,.0f} บาท")
        lines.append(f"\n💰 รวมทั้งเดือน: {total:,.0f} บาท")

        reply_text(reply_token, "\n".join(lines))
        return "weekly ok", 200

    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, category = parts
            elif len(parts) == 2:
                item, amount = parts
                category = "-"
            else:
                continue
            amount = float(amount)
            records.append((user_id, item.strip(), amount, category.strip(), today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: ค่าน้ำ 120 ของใช้")
        return "format error", 200

    conn.executemany("INSERT INTO expenses VALUES (?, ?, ?, ?, ?)", records)
    conn.commit()

    rows = conn.execute(
        "SELECT item, amount, category FROM expenses WHERE user_id=? AND date=?",
        (user_id, today_str)).fetchall()

    month_total = conn.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date LIKE ?",
        (user_id, f"{month_prefix}-%")).fetchone()[0] or 0

    conn.close()

    total_today = sum(r[1] for r in rows)
    lines = [f"📅 รายจ่ายวันนี้ ({today_display})"]
    for r in rows:
        if r[2] != "-":
            lines.append(f"- {r[0]}: {r[1]:,.0f} บาท ({r[2]})")
        else:
            lines.append(f"- {r[0]}: {r[1]:,.0f} บาท")
    lines.append(f"\n💸 รวมวันนี้: {total_today:,.0f} บาท")
    lines.append(f"🗓 รวมเดือนนี้: {month_total:,.0f} บาท")

    reply_text(reply_token, "\n".join(lines))
    return "OK", 200

@app.route("/export", methods=["GET"])
def export_excel():
    conn = sqlite3.connect("runtime.db")
    rows = conn.execute("SELECT user_id, item, amount, category, date FROM expenses").fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["User", "Item", "Amount", "Category", "Date"])
    for user_id, item, amount, category, date in rows:
        user = get_user_name(user_id)
        show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        ws.append([user, item, amount, category, show_date])

    file_path = "expenses_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
