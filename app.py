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
        df = pd.read_sql_query("SELECT * FROM records", conn)
        if df.empty:
            reply_text(reply_token, "❌ ไม่มีข้อมูลในระบบ")
            return "no data", 200

        wb = Workbook()
        # รายรับ
        ws1 = wb.active
        ws1.title = "Income"
        ws1.append(["User", "Item", "Amount", "Category", "Date"])
        for row in df[df['type'] == 'income'].itertuples():
            ws1.append([get_user_name(row.user_id), row.item, row.amount, row.category, row.date])
        # รายจ่าย
        ws2 = wb.create_sheet(title="Expense")
        ws2.append(["User", "Item", "Amount", "Category", "Date"])
        for row in df[df['type'] == 'expense'].itertuples():
            ws2.append([get_user_name(row.user_id), row.item, row.amount, row.category, row.date])

        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # --- รวมรายได้ตามช่วงวันที่ ---
    if msg.lower().startswith("รวมรายได้"):
        try:
            date_part = msg.strip().split(" ")[-1].replace(" ", "")
            d1, d2 = date_part.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records WHERE type='income'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, "❌ ไม่พบข้อมูลรายได้")
                return "ok", 200
            summary = df.groupby("item")["amount"].sum()
            total = df["amount"].sum()
            lines = [
                f"📅 รายได้ {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}",
                f"💵 รายได้รวม: {total:,.0f} บาท"
            ]
            for item, amt in summary.items():
                lines.append(f"• {item}: {amt:,.0f} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รวมรายได้ 1-7/06/2025")
            return "bad", 200

    # --- รวมรายจ่ายตามช่วงวันที่ ---
    if msg.lower().startswith("รวมรายจ่าย"):
        try:
            date_part = msg.strip().split(" ")[-1].replace(" ", "")
            d1, d2 = date_part.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records WHERE type='expense'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, "❌ ไม่พบข้อมูลรายจ่าย")
                return "ok", 200
            total = df["amount"].sum()
            lines = [
                f"📅 รายจ่าย {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}",
                f"💸 รายจ่ายรวม: {total:,.0f} บาท"
            ]
            reply_text(reply_token, "\n".join(lines))
            return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รวมรายจ่าย 1-7/06/2025")
            return "bad", 200

    # --- DELETE ---
    if msg.lower().startswith("ลบรายได้ "):
        date_text = msg[10:].strip()
        try:
            dt = datetime.strptime(date_text, "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type='income'", (user_id, dt))
            conn.commit()
            reply_text(reply_token, f"🗑 ลบรายได้วันที่ {date_text} แล้ว")
            return "deleted", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: ลบรายได้ 01-06-2025")
            return "fail", 200

    if msg.lower().startswith("ลบรายจ่าย "):
        date_text = msg[11:].strip()
        try:
            dt = datetime.strptime(date_text, "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type='expense'", (user_id, dt))
            conn.commit()
            reply_text(reply_token, f"🗑 ลบรายจ่ายวันที่ {date_text} แล้ว")
            return "deleted", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: ลบรายจ่าย 01-06-2025")
            return "fail", 200

    # --- PARSE INCOME ---
    if msg.startswith("รายวันที่"):
        try:
            lines = msg.strip().split("\n")
            date_str = lines[0].replace("รายวันที่", "").strip()
            record_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            display_date = datetime.strptime(record_date, "%Y-%m-%d").strftime("%d-%m-%Y")
            income_items = []
            for line in lines[1:]:
                if "รายได้" in line:
                    if "รวม" in line:
                        income_items.append(("รายได้รวม", float(line.split(" ")[-1]), "รวม"))
                    elif "อาหาร" in line:
                        income_items.append(("รายได้อาหาร", float(line.split(" ")[-1]), "อาหาร"))
                    elif "เครื่องดื่ม" in line:
                        income_items.append(("รายได้เครื่องดื่ม", float(line.split(" ")[-1]), "เครื่องดื่ม"))
                elif "แยกรายได้" in line:
                    label = line.replace("แยกรายได้", "").split(" ")[0]
                    amt = float(line.split(" ")[-1])
                    income_items.append((f"แยกรายได้{label}", amt, label))

            if not income_items:
                reply_text(reply_token, "❌ ไม่พบข้อมูลรายได้ที่สามารถบันทึกได้")
                return "fail", 200

            for item, amt, cat in income_items:
                conn.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                             (user_id, item, amt, cat, "income", record_date))
            conn.commit()
            by_cat = {}
            for item, amt, cat in income_items:
                if cat not in by_cat:
                    by_cat[cat] = 0
                by_cat[cat] += amt

            reply = [f"📅 บันทึกวันที่ {display_date}"]
            reply.append(f"💵 รายได้รวม: {by_cat.get('รวม', 0):,} บาท")
            reply.append(f"🍟 รายได้อาหาร: {by_cat.get('อาหาร', 0):,} บาท")
            reply.append(f"🍺 รายได้เครื่องดื่ม: {by_cat.get('เครื่องดื่ม', 0):,} บาท\n")
            reply.append(f"📌 โอน: {by_cat.get('โอน', 0):,} บาท")
            reply.append(f"📌 เงินสด: {by_cat.get('เงินสด', 0):,} บาท")
            reply.append(f"📌 เครดิต: {by_cat.get('เครดิต', 0):,} บาท")
            reply_text(reply_token, "\n".join(reply))
            return "ok", 200
        except:
            reply_text(reply_token, "❌ เกิดข้อผิดพลาดขณะบันทึกรายได้")
            return "fail", 200

    # --- PARSE EXPENSE ---
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
            amount = float(amount.replace(",", ""))
            records.append((user_id, item.strip(), amount, category.strip(), "expense", today_str))
        except:
            continue

    if records:
        conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
        conn.commit()
        total = sum([r[2] for r in records])
        lines = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for r in records:
            if r[3] != "-":
                lines.append(f"- {r[1]}: {r[2]:,.0f} บาท ({r[3]})")
            else:
                lines.append(f"- {r[1]}: {r[2]:,.0f} บาท")
        lines.append(f"\n💸 รวมวันนี้: {total:,.0f} บาท")
        reply_text(reply_token, "\n".join(lines))
        return "ok", 200

    reply_text(reply_token, "❌ ไม่พบข้อมูลที่สามารถบันทึกได้")
    return "fail", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
