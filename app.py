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
        conn.close()

        wb = Workbook()
        ws_income = wb.active
        ws_income.title = "Income"
        ws_expense = wb.create_sheet("Expense")
        ws_income.append(["User", "Item", "Amount", "Category", "Date"])
        ws_expense.append(["User", "Item", "Amount", "Category", "Date"])

        for user_id, item, amount, category, dtype, date in rows:
            user = get_user_name(user_id)
            show_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
            row_data = [user, item, amount, category, show_date]
            if dtype == "income":
                ws_income.append(row_data)
            else:
                ws_expense.append(row_data)

        file_path = "records_export.xlsx"
        wb.save(file_path)
        return send_file(file_path, as_attachment=True)

    # --- รวมรายได้ / รายจ่าย ---
    if msg.lower().startswith("รวมรายได้ ") or msg.lower().startswith("รวมรายจ่าย "):
        try:
            is_income = "รายได้" in msg
            date_range = msg.split(" ")[1]
            start, end = date_range.split("-")
            d1 = datetime.strptime(start + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(end + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            df = df[df["type"] == ("income" if is_income else "expense")]
            
            if df.empty:
                reply_text(reply_token, "❌ ไม่พบข้อมูลในช่วงวันที่ที่ระบุ")
                return "no data", 200

            grouped = df.groupby(["item"])["amount"].sum()
            total = df["amount"].sum()
            header = "💵 รายได้" if is_income else "💸 รายจ่าย"
            lines = [f"{header} {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')}" + "\n"]
            for item, amt in grouped.items():
                lines.append(f"• {item}: {amt:,.0f} บาท")
            lines.append(f"\n📌 รวมทั้งหมด: {total:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "summary", 200
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รวมรายได้ 1-7/06/2025")
            return "parse error", 200

    # --- บันทึกรายได้ ---
    lines = msg.strip().split("\n")
    if lines[0].startswith("รายวันที่"):
        date_obj = datetime.strptime(lines[0].split(" ")[1], "%d/%m/%Y")
        date_str = date_obj.strftime("%Y-%m-%d")
        summary = {"รวม": 0, "อาหาร": 0, "เครื่องดื่ม": 0, "โอน": 0, "เงินสด": 0, "เครดิต": 0}
        records = []
        for line in lines[1:]:
            try:
                item, amount = line.rsplit(" ", 1)
                amount = float(amount.replace(",", ""))
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
                records.append((user_id, item.strip(), amount, "-", "income", date_str))
            except:
                continue
        if records:
            conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
            conn.commit()
            reply = [
                f"📅 บันทึกวันที่ {date_obj.strftime('%d-%m-%Y')}",
                f"\n💵 รายได้รวม: {summary['รวม']:,.0f} บาท",
                f"🍟 รายได้อาหาร: {summary['อาหาร']:,.0f} บาท",
                f"🍺 รายได้เครื่องดื่ม: {summary['เครื่องดื่ม']:,.0f} บาท",
                f"\n📌 โอน: {summary['โอน']:,.0f} บาท",
                f"📌 เงินสด: {summary['เงินสด']:,.0f} บาท",
                f"📌 เครดิต: {summary['เครดิต']:,.0f} บาท"
            ]
            reply_text(reply_token, "\n".join(reply))
            return "income saved", 200

    # --- ลบข้อมูล ---
    if msg.startswith("ลบรายได้ ") or msg.startswith("ลบรายจ่าย "):
        try:
            date_input = msg.split(" ")[1]
            date_obj = datetime.strptime(date_input, "%d-%m-%Y")
            date_str = date_obj.strftime("%Y-%m-%d")
            del_type = "income" if "รายได้" in msg else "expense"
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type=?", (user_id, date_str, del_type))
            conn.commit()
            reply_text(reply_token, f"🧹 ลบ{del_type} วันที่ {date_input} เรียบร้อยแล้ว")
            return "delete done", 200
        except:
            reply_text(reply_token, "❌ ลบไม่สำเร็จ รูปแบบผิด เช่น: ลบรายได้ 01-06-2025")
            return "delete error", 200

    # --- รายจ่ายทั่วไป ---
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
            amount = float(amount.replace(",", ""))
            records.append((user_id, item.strip(), amount, category.strip(), "expense", today_str))
        except:
            continue

    if records:
        conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
        conn.commit()
        df = pd.DataFrame(records, columns=["user_id", "item", "amount", "category", "type", "date"])
        total_today = df["amount"].sum()
        month_prefix = today.strftime('%Y-%m')
        cur = conn.cursor()
        cur.execute("SELECT SUM(amount) FROM records WHERE user_id=? AND type='expense' AND date LIKE ?", (user_id, f"{month_prefix}-%"))
        month_total = cur.fetchone()[0] or 0
        conn.close()
        reply = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for _, row in df.iterrows():
            if row["category"] != "-":
                reply.append(f"- {row['item']}: {row['amount']:.0f} บาท ({row['category']})")
            else:
                reply.append(f"- {row['item']}: {row['amount']:.0f} บาท")
        reply.append(f"\n📌 รวมวันนี้: {total_today:,.0f} บาท")
        reply.append(f"📆 รวมเดือนนี้: {month_total:,.0f} บาท")
        reply_text(reply_token, "\n".join(reply))
        return "expense saved", 200

    reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: ข้าว 50 อาหาร หรือ รายได้รวม 10000 รายได้")
    return "invalid format", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
