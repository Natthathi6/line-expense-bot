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
        reply_text(reply_token, f"📥 ไฟล์ export เสร็จแล้ว ดาวน์โหลดได้ที่:\nhttps://{request.host}/records_export.xlsx")
        return "export ok", 200

    if msg.lower().startswith("รวมรายได้"):
        try:
            _, range_str = msg.split("รวมรายได้")
            d1_str, d2_str = range_str.strip().split("-")
            d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
            d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
            df = pd.read_sql_query(f"SELECT * FROM records WHERE type='income'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, f"📍 ไม่มีรายได้ในช่วงที่ระบุ")
                return "no data", 200
            summary = {
                "อาหาร": df[df["category"] == "อาหาร"]["amount"].sum(),
                "เครื่องดื่ม": df[df["category"] == "เครื่องดื่ม"]["amount"].sum(),
                "โอน": df[df["category"] == "โอน"]["amount"].sum(),
                "เงินสด": df[df["category"] == "เงินสด"]["amount"].sum(),
                "เครดิต": df[df["category"] == "เครดิต"]["amount"].sum()
            }
            sum_category = summary["อาหาร"] + summary["เครื่องดื่ม"]
            reply = [
                f"📅 รวมรายได้ {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}",
                f"💵 รายได้รวม: {sum_category:,.0f} บาท",
                f"🍟 รายได้อาหาร: {summary['อาหาร']:,.0f} บาท",
                f"🍺 รายได้เครื่องดื่ม: {summary['เครื่องดื่ม']:,.0f} บาท",
                "",
                f"📌 โอน: {summary['โอน']:,.0f} บาท",
                f"📌 เงินสด: {summary['เงินสด']:,.0f} บาท",
                f"📌 เครดิต: {summary['เครดิต']:,.0f} บาท"
            ]
            reply_text(reply_token, "\n".join(reply))
            return "sum income ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายได้ 1 Jun 2025 - 10 Jun 2025")
            return "invalid", 200

    if msg.lower().startswith("รวมรายจ่าย"):
        try:
            _, range_str = msg.split("รวมรายจ่าย")
            d1_str, d2_str = range_str.strip().split("-")
            d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
            d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
            df = pd.read_sql_query(f"SELECT * FROM records WHERE type='expense'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, f"📍 ไม่มีรายจ่ายในช่วงที่ระบุ")
                return "no data", 200
            total = df["amount"].sum()
            df = df.sort_values(by="date")
            lines = [
                f"📅 รายจ่าย {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}: {total:,.0f} บาท",
                ""
            ]
            for _, row in df.iterrows():
                date_show = row["date"].strftime('%d-%m')
                if row["category"] != "-":
                    lines.append(f"{date_show} - {row['item']}: {row['amount']:,.0f} บาท ({row['category']})")
                else:
                    lines.append(f"{date_show} - {row['item']}: {row['amount']:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "sum expense ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายจ่าย 1 Jun 2025 - 10 Jun 2025")
            return "invalid", 200

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
