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

def fmt(value):
    return '{:,.2f}'.format(value).rstrip('0').rstrip('.') + ' บาท'

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

        ws_income = wb.active
        ws_income.title = "Income"
        ws_income.append(["User", "Item", "Amount", "Category", "Date"])

        ws_expense = wb.create_sheet("Expense")
        ws_expense.append(["User", "Item", "Amount", "Category", "Date"])

        for user_id, item, amount, category, dtype, date in rows:
            user = get_user_name(user_id)
            show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
            if dtype == "income":
                ws_income.append([user, item, amount, category, show_date])
            else:
                ws_expense.append([user, item, amount, category, show_date])

        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # --- SUMMARIZE BY DATE RANGE ---
    if msg.startswith("รวมรายได้ ") or msg.startswith("รวมรายจ่าย "):
        try:
            is_income = "รายได้" in msg
            date_range = msg.replace("รวมรายได้ ", "").replace("รวมรายจ่าย ", "").strip()
            d1, d2 = date_range.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            d1_str, d2_str = d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d")

            df = pd.read_sql_query("SELECT * FROM records", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            df = df[df["type"] == ("income" if is_income else "expense")]

            if df.empty:
                reply_text(reply_token, "📍 ไม่มีข้อมูลในช่วงที่ระบุ")
                return "no data", 200

            total = df["amount"].sum()
            reply = [f"📊 {'รายได้' if is_income else 'รายจ่าย'} {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')} ({get_user_name(user_id)})"]

            for cat, amt in df.groupby("category")["amount"].sum().items():
                label = f"{'💵 รายได้' if is_income else '💸 รายจ่าย'}{'' if cat == '-' else f'({cat})'}"
                reply.append(f"{label}: {fmt(amt)}")

            reply.append(f"\n📌 รวมทั้งหมด: {fmt(total)}")
            reply_text(reply_token, "\n".join(reply))
            return "range summary", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายได้ 1-6/06/2025")
            return "parse error", 200

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
                    category = final
                    type_ = "expense"
            elif len(parts) == 2:
                item, amount = parts
                category = "-"
                type_ = "expense"
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
        reply = [
            f"📅 บันทึกวันที่ {today_display}",
            f"💵 รายได้รวม: {fmt(summary['รวม'])}",
            f"🍟 รายได้อาหาร: {fmt(summary['อาหาร'])}",
            f"🍺 รายได้เครื่องดื่ม: {fmt(summary['เครื่องดื่ม'])}",
            "",
            f"📌 โอน: {fmt(summary['โอน'])}",
            f"📌 เงินสด: {fmt(summary['เงินสด'])}",
            f"📌 เครดิต: {fmt(summary['เครดิต'])}"
        ]
        reply_text(reply_token, "\n".join(reply))
        return "OK", 200
    else:
        total_today = conn.execute("SELECT SUM(amount) FROM records WHERE user_id=? AND date=? AND type='expense'", (user_id, today_str)).fetchone()[0] or 0
        month_prefix = today.strftime('%Y-%m')
        month_total = conn.execute("SELECT SUM(amount) FROM records WHERE user_id=? AND date LIKE ? AND type='expense'", (user_id, f"{month_prefix}-%")).fetchone()[0] or 0
        today_rows = conn.execute("SELECT item, amount, category FROM records WHERE user_id=? AND date=? AND type='expense'", (user_id, today_str)).fetchall()

        reply = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for r in today_rows:
            item, amount, cat = r
            if cat != "-":
                reply.append(f"- {item}: {fmt(amount)} ({cat})")
            else:
                reply.append(f"- {item}: {fmt(amount)}")
        reply.append(f"\n💸 รวมวันนี้: {fmt(total_today)}")
        reply.append(f"🗓 รวมเดือนนี้: {fmt(month_total)}")
        reply_text(reply_token, "\n".join(reply))
        return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
