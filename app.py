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

@app.route("/records_export.xlsx")
def download_export_file():
    return send_file("records_export.xlsx", as_attachment=True)

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

    def parse_date(date_str):
        for fmt in ["%d/%m/%Y", "%d %b %Y"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except:
                continue
        return None

    # EXPORT
    if msg.lower().strip() == "export":
        rows = conn.execute("SELECT user_id, item, amount, category, type, date FROM records").fetchall()
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Income"
        ws1.append(["User", "Item", "Amount", "Category", "Date"])
        for r in rows:
            if r[4] == "income":
                ws1.append([get_user_name(r[0]), r[1], r[2], r[3], datetime.strptime(r[5], "%Y-%m-%d").strftime("%d-%m-%Y")])
        ws2 = wb.create_sheet(title="Expense")
        ws2.append(["User", "Item", "Amount", "Category", "Date"])
        for r in rows:
            if r[4] == "expense":
                ws2.append([get_user_name(r[0]), r[1], r[2], r[3], datetime.strptime(r[5], "%Y-%m-%d").strftime("%d-%m-%Y")])
        file_path = "records_export.xlsx"
        wb.save(file_path)
        reply_text(reply_token, f"\U0001F4E5 ไฟล์ export เสร็จแล้ว ดาวน์โหลดได้ที่:\nhttps://{request.host}/records_export.xlsx")
        return "export ok", 200

    # ลบรายได้ / รายจ่าย ตามช่วงวันที่
    for keyword, ttype in [("ลบรายได้", "income"), ("ลบรายจ่าย", "expense")]:
        if msg.lower().startswith(keyword):
            try:
                _, range_str = msg.split(keyword)
                d1_str, d2_str = range_str.strip().split("-")
                d1 = parse_date(d1_str)
                d2 = parse_date(d2_str)
                if not d1 or not d2:
                    raise ValueError("invalid date")
                conn.execute("DELETE FROM records WHERE user_id=? AND type=? AND date BETWEEN ? AND ?",
                             (user_id, ttype, d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d")))
                conn.commit()
                reply_text(reply_token, f"\U0001F9F9 ลบ{ttype}ระหว่าง {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')} แล้ว")
                return "deleted", 200
            except:
                reply_text(reply_token, f"❌ รูปแบบผิด เช่น: {keyword} 1-10 Jun 2025")
                return "invalid del", 200

    # รวมรายได้/รายจ่าย
    for keyword, ttype, icon in [("รวมรายได้", "income", "\U0001F4B5"), ("รวมรายจ่าย", "expense", "\U0001F4B8")]:
        if msg.lower().startswith(keyword):
            try:
                _, range_str = msg.split(keyword)
                d1_str, d2_str = range_str.strip().split("-")
                d1 = parse_date(d1_str)
                d2 = parse_date(d2_str)
                if not d1 or not d2:
                    raise ValueError("invalid date")
                df = pd.read_sql_query(f"SELECT * FROM records WHERE type='{ttype}'", conn)
                df["date"] = pd.to_datetime(df["date"])
                df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
                if df.empty:
                    reply_text(reply_token, f"📍 ไม่มี{ttype}ในช่วงที่ระบุ")
                    return "no data", 200
                total = df["amount"].sum()
                reply_text(reply_token, f"{icon} รวม{ttype} {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}: {total:,.0f} บาท")
                return "sum ok", 200
            except:
                reply_text(reply_token, f"❌ รูปแบบผิด เช่น: {keyword} 1-10 Jun 2025")
                return "invalid", 200

    # รายได้ pattern พิเศษ
    if msg.startswith("รายวันที่"):
        try:
            lines = msg.strip().split("\n")
            date_str = lines[0].replace("รายวันที่", "").strip()
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
            summary = {"รวม": 0, "อาหาร": 0, "เครื่องดื่ม": 0, "โอน": 0, "เงินสด": 0, "เครดิต": 0}
            records = []
            for line in lines[1:]:
                for key in summary:
                    if f"รายได้{key}" in line or f"แยกรายได้{key}" in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            try:
                                amount = float(parts[1].replace(",", ""))
                                summary[key] += amount
                                records.append((user_id, parts[0], amount, key, "income", date_iso))
                            except:
                                continue
            if records:
                conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
                conn.commit()
                lines = [f"📅 บันทึกวันที่ {date_obj.strftime('%d-%m-%Y')}",
                         f"💵 รายได้รวม: {summary['รวม']:,.0f} บาท",
                         f"🍟 รายได้อาหาร: {summary['อาหาร']:,.0f} บาท",
                         f"🍺 รายได้เครื่องดื่ม: {summary['เครื่องดื่ม']:,.0f} บาท",
                         "",
                         f"📌 โอน: {summary['โอน']:,.0f} บาท",
                         f"📌 เงินสด: {summary['เงินสด']:,.0f} บาท",
                         f"📌 เครดิต: {summary['เครดิต']:,.0f} บาท"]
                reply_text(reply_token, "\n".join(lines))
                return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายวันที่ 01/06/2025")
            return "invalid", 200

    # รายจ่ายทั่วไป
    lines = msg.strip().split("\n")
    records = []
    for line in lines:
        parts = line.rsplit(" ", 2)
        if len(parts) == 3:
            item, amount, category = parts
        elif len(parts) == 2:
            item, amount = parts
            category = "-"
        else:
            continue
        try:
            amount = float(amount.replace(",", ""))
            records.append((user_id, item.strip(), amount, category.strip(), "expense", today.strftime("%Y-%m-%d")))
        except:
            continue

    if records:
        conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
        conn.commit()
        df = pd.read_sql_query("SELECT item, amount, category FROM records WHERE user_id=? AND date=? AND type='expense'", conn, params=(user_id, today_str))
        total_today = df["amount"].sum()
        reply = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for _, row in df.iterrows():
            if row["category"] != "-":
                reply.append(f"- {row['item']}: {row['amount']:,.0f} บาท ({row['category']})")
            else:
                reply.append(f"- {row['item']}: {row['amount']:,.0f} บาท")
        reply.append(f"\n💸 รวมวันนี้: {total_today:,.0f} บาท")
        reply_text(reply_token, "\n".join(reply))
        return "ok", 200

    reply_text(reply_token, "❌ ไม่พบข้อมูลที่สามารถบันทึกได้")
    return "fail", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
