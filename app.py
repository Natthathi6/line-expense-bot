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

    # EXPORT COMMAND
    if msg.lower().strip() == "export":
        df = pd.read_sql_query("SELECT * FROM records", conn)
        wb = Workbook()

        for record_type in ['income', 'expense']:
            ws = wb.create_sheet(title=record_type.capitalize())
            ws.append(["User", "Item", "Amount", "Category", "Date"])
            df_filtered = df[df["type"] == record_type]
            for _, row in df_filtered.iterrows():
                ws.append([
                    get_user_name(row['user_id']), row['item'], row['amount'], row['category'],
                    datetime.strptime(row['date'], "%Y-%m-%d").strftime("%d-%m-%Y")
                ])

        wb.remove(wb["Sheet"])
        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # REMOVE RECORDS BY DATE
    if msg.startswith("ลบรายจ่าย ") or msg.startswith("ลบรายได้ "):
        try:
            dtype = "expense" if "รายจ่าย" in msg else "income"
            input_date = msg.split()[1]
            db_date = datetime.strptime(input_date, "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type=?", (user_id, db_date, dtype))
            conn.commit()
            reply_text(reply_token, f"🗑 ลบ{dtype}ของวันที่ {input_date} แล้ว")
            return "deleted", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: ลบรายจ่าย 01-06-2025")
            return "format error", 200

    # SUM BY DATE RANGE
    if msg.startswith("รวมรายได้ ") or msg.startswith("รวมรายจ่าย "):
        try:
            dtype = "income" if "รายได้" in msg else "expense"
            _, date_range = msg.split(" ", 1)
            d1, d2 = date_range.strip().split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")

            df = pd.read_sql_query("SELECT * FROM records WHERE user_id=? AND type=?", conn, params=(user_id, dtype))
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= d1) & (df["date"] <= d2)]

            if df.empty:
                reply_text(reply_token, "📍 ไม่มีข้อมูลในช่วงเวลานี้")
                return "no data", 200

            summary = df.groupby("category")["amount"].sum()
            lines = [f"📅 {dtype.capitalize()} {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')} ({get_user_name(user_id)})"]
            for cat, amt in summary.items():
                emoji = "💵" if dtype == "income" else "💸"
                lines.append(f"{emoji} {cat if cat != '-' else 'ทั่วไป'}: {amt:,.0f} บาท")
            total = df["amount"].sum()
            lines.append(f"\n📊 รวม: {total:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "summary", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายได้ 1-6/06/2025")
            return "error", 200

    # RECORD DATA
    lines = msg.strip().split("\n")
    records = []
    current_date = today_str

    for line in lines:
        if line.startswith("รายวันที่"):
            try:
                current_date = datetime.strptime(line.replace("รายวันที่", "").strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                continue
        else:
            try:
                parts = line.strip().split()
                amount = float(parts[-1].replace(",", ""))
                text = " ".join(parts[:-1])

                if text.startswith("รายได้"):
                    cat = text.replace("รายได้", "").strip() or "รวม"
                    records.append((user_id, cat, amount, cat, "income", current_date))
                elif text.startswith("แยกรายได้"):
                    cat = text.replace("แยกรายได้", "").strip()
                    records.append((user_id, cat, amount, cat, "income", current_date))
                else:
                    if len(parts) >= 3:
                        item = " ".join(parts[:-2])
                        category = parts[-2]
                    else:
                        item = " ".join(parts[:-1])
                        category = "-"
                    records.append((user_id, item, amount, category, "expense", current_date))
            except:
                continue

    if not records:
        reply_text(reply_token, "❌ ไม่พบข้อมูลที่สามารถบันทึกได้")
        return "invalid", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()

    df = pd.DataFrame(records, columns=["user_id", "item", "amount", "category", "type", "date"])

    # REPLY
    if all(df["type"] == "income"):
        summary = {
            "รวม": 0, "อาหาร": 0, "เครื่องดื่ม": 0,
            "โอน": 0, "เงินสด": 0, "เครดิต": 0
        }
        for _, row in df.iterrows():
            k = row["category"]
            if k in summary:
                summary[k] += row["amount"]
        reply = [
            f"📅 บันทึกวันที่ {datetime.strptime(current_date, '%Y-%m-%d').strftime('%d-%m-%Y')}",
            f"💵 รายได้รวม: {summary['รวม']:,.0f} บาท",
            f"🍟 รายได้อาหาร: {summary['อาหาร']:,.0f} บาท",
            f"🍺 รายได้เครื่องดื่ม: {summary['เครื่องดื่ม']:,.0f} บาท",
            "",
            f"📌 โอน: {summary['โอน']:,.0f} บาท",
            f"📌 เงินสด: {summary['เงินสด']:,.0f} บาท",
            f"📌 เครดิต: {summary['เครดิต']:,.0f} บาท"
        ]
        reply_text(reply_token, "\n".join(reply))
    else:
        this_date = df["date"].iloc[0]
        df_all = pd.read_sql_query("SELECT * FROM records WHERE user_id=? AND type='expense'", conn, params=(user_id,))
        df_all["date"] = pd.to_datetime(df_all["date"])
        df_today = df_all[df_all["date"] == this_date]
        df_month = df_all[df_all["date"].dt.strftime("%Y-%m") == this_date[:7]]

        lines = [f"📅 รายจ่ายวันที่ {datetime.strptime(this_date, '%Y-%m-%d').strftime('%d-%m-%Y')}"]
        for _, row in df_today.iterrows():
            lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท ({row['category']})" if row['category'] != "-" else f"- {row['item']}: {row['amount']:,.0f} บาท")
        lines.append(f"\n💸 รวมวันนี้: {df_today['amount'].sum():,.0f} บาท")
        lines.append(f"📊 รวมเดือนนี้: {df_month['amount'].sum():,.0f} บาท")
        reply_text(reply_token, "\n".join(lines))

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
