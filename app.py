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
        income_ws = wb.active
        income_ws.title = "Income"
        income_ws.append(["User", "Item", "Amount", "Category", "Date"])
        expense_ws = wb.create_sheet("Expense")
        expense_ws.append(["User", "Item", "Amount", "Category", "Date"])
        for user_id, item, amount, category, dtype, date in rows:
            user = get_user_name(user_id)
            show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
            sheet = income_ws if dtype == "income" else expense_ws
            sheet.append([user, item, amount, category, show_date])
        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # --- DELETE ---
    if msg.startswith("ลบรายได้ "):
        try:
            d = datetime.strptime(msg[10:], "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type='income'", (user_id, d))
            conn.commit()
            reply_text(reply_token, f"✅ ลบรายได้วันที่ {msg[10:]} แล้ว")
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ผิด เช่น ลบรายได้ 01-06-2025")
        return "ok", 200

    if msg.startswith("ลบรายจ่าย "):
        try:
            d = datetime.strptime(msg[11:], "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type='expense'", (user_id, d))
            conn.commit()
            reply_text(reply_token, f"✅ ลบรายจ่ายวันที่ {msg[11:]} แล้ว")
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ผิด เช่น ลบรายจ่าย 01-06-2025")
        return "ok", 200

    # --- รวมรายได้ / รายจ่ายตามช่วงวันที่ ---
    if msg.startswith("รวมรายได้ ") or msg.startswith("รวมรายจ่าย "):
        try:
            text = msg.replace("รวมรายได้ ", "").replace("รวมรายจ่าย ", "")
            date_range = text.strip()
            start, end = date_range.split("-")
            start = datetime.strptime(start.strip() + "/2025", "%d/%m/%Y")
            end = datetime.strptime(end.strip() + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= start) & (df["date"] <= end)]
            if msg.startswith("รวมรายได้"):
                df = df[df["type"] == "income"]
            else:
                df = df[df["type"] == "expense"]
            if df.empty:
                reply_text(reply_token, "📭 ไม่พบข้อมูลในช่วงวันที่ที่ระบุ")
                return "no data", 200
            total = df["amount"].sum()
            group = df.groupby(["item"])["amount"].sum()
            lines = [f"📆 {msg.strip()} ({start.strftime('%d/%m')} - {end.strftime('%d/%m')})"]
            for item, amt in group.items():
                lines.append(f"- {item}: {amt:,.0f} บาท")
            lines.append(f"\n💰 รวม: {total:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น รวมรายได้ 1-7/06/2025")
        return "ok", 200

    # --- INSERT INCOME ---
    if msg.startswith("รายวันที่"):
        lines = msg.split("\n")
        try:
            date_line = lines[0].replace("รายวันที่", "").strip()
            date_obj = datetime.strptime(date_line, "%d/%m/%Y")
            date_str = date_obj.strftime("%Y-%m-%d")
        except:
            reply_text(reply_token, "❌ รูปแบบวันที่ผิด เช่น รายวันที่ 01/06/2025")
            return "invalid", 200
        income_map = {
            "รวม": 0,
            "อาหาร": 0,
            "เครื่องดื่ม": 0,
            "โอน": 0,
            "เงินสด": 0,
            "เครดิต": 0
        }
        rows = []
        for l in lines[1:]:
            for key in income_map:
                if f"รายได้{key}" in l or f"แยกรายได้{key}" in l:
                    try:
                        amount = float(l.split()[1].replace(",", ""))
                        income_map[key] += amount
                        rows.append((user_id, f"รายได้{key}", amount, key, "income", date_str))
                    except:
                        continue
        if not rows:
            reply_text(reply_token, "❌ ไม่พบข้อมูลรายได้ในข้อความ")
            return "no income", 200
        conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        reply = [f"📅 บันทึกวันที่ {date_obj.strftime('%d-%m-%Y')}"]
        reply.append(f"\n💵 รายได้รวม: {income_map['รวม']:,} บาท")
        reply.append(f"🍟 รายได้อาหาร: {income_map['อาหาร']:,} บาท")
        reply.append(f"🍺 รายได้เครื่องดื่ม: {income_map['เครื่องดื่ม']:,} บาท")
        reply.append("")
        reply.append(f"📌 โอน: {income_map['โอน']:,} บาท")
        reply.append(f"📌 เงินสด: {income_map['เงินสด']:,} บาท")
        reply.append(f"📌 เครดิต: {income_map['เครดิต']:,} บาท")
        reply_text(reply_token, "\n".join(reply))
        return "ok", 200

    # --- DEFAULT: Expense ---
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        try:
            parts = line.strip().rsplit(" ", 2)
            if len(parts) == 3:
                item, amount, cat = parts
            elif len(parts) == 2:
                item, amount = parts
                cat = "-"
            else:
                continue
            amount = float(amount.replace(",", ""))
            records.append((user_id, item.strip(), amount, cat.strip(), "expense", today_str))
        except:
            continue
    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: ค่าตลาด 500 ของครัว")
        return "bad", 200
    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    df = pd.read_sql_query("SELECT item, amount, category FROM records WHERE user_id=? AND date=? AND type='expense'", conn, params=(user_id, today_str))
    if df.empty:
        reply_text(reply_token, "📭 ไม่พบรายจ่ายวันนี้")
        return "empty", 200
    total_today = df["amount"].sum()
    df_month = pd.read_sql_query("SELECT amount FROM records WHERE user_id=? AND type='expense' AND date LIKE ?", conn, params=(user_id, today_str[:7] + '%'))
    total_month = df_month["amount"].sum()
    lines = [f"📅 รายจ่ายวันนี้ ({today_display})"]
    for _, row in df.iterrows():
        if row['category'] != "-":
            lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท ({row['category']})")
        else:
            lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท")
    lines.append(f"\n💸 รวมวันนี้: {total_today:,.0f} บาท")
    lines.append(f"🗓 รวมเดือนนี้: {total_month:,.0f} บาท")
    reply_text(reply_token, "\n".join(lines))
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
