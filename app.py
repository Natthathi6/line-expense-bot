from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
import requests
from openpyxl import Workbook
import pandas as pd

app = Flask(__name__)
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")

CATEGORIES = ["อาหาร", "เครื่องดื่ม"]
PAYMENTS = ["โอน", "เงินสด", "เครดิต"]


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

    # --- EXPORT ---
    if msg.lower().strip() == "export":
        rows = conn.execute("SELECT user_id, item, amount, category, type, date FROM records").fetchall()
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Income"
        ws1.append(["User", "Item", "Amount", "Category", "Date"])
        for user_id, item, amount, category, typ, date in rows:
            if typ != "income":
                continue
            ws1.append([get_user_name(user_id), item, amount, category, date])

        ws2 = wb.create_sheet("Expense")
        ws2.append(["User", "Item", "Amount", "Category", "Date"])
        for user_id, item, amount, category, typ, date in rows:
            if typ != "expense":
                continue
            ws2.append([get_user_name(user_id), item, amount, category, date])

        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # --- DELETE INCOME / EXPENSE ---
    if msg.lower().startswith("del "):
        parts = msg.strip().split()
        if len(parts) == 3 and parts[1] in ["income", "expense"]:
            try:
                date_obj = datetime.strptime(parts[2], "%d-%m-%Y")
                db_date = date_obj.strftime("%Y-%m-%d")
                conn.execute("DELETE FROM records WHERE user_id=? AND date=? AND type=?", (user_id, db_date, parts[1]))
                conn.commit()
                reply_text(reply_token, f"🧹 ลบ {parts[1]} วันที่ {parts[2]} เรียบร้อย")
                return "deleted", 200
            except:
                reply_text(reply_token, "❌ รูปแบบผิด เช่น: del income 01-06-2025")
                return "invalid delete", 200

    # --- SUMMARIES ---
    if msg.startswith("รวมรายได้") or msg.startswith("รวมรายจ่าย"):
        try:
            label = "income" if "รายได้" in msg else "expense"
            date_str = msg.split(" ")[-1].replace("/", "-")
            d1, d2 = date_str.split("-")
            d1 = datetime.strptime(d1, "%d-%m-%Y")
            d2 = datetime.strptime(d2, "%d-%m-%Y")
            d1_str, d2_str = d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d")
            df = pd.read_sql_query("SELECT * FROM records", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["type"] == label) & (df["date"] >= d1) & (df["date"] <= d2)]
            total = df["amount"].sum()
            reply = [f"📅 รวม{('รายได้' if label=='income' else 'รายจ่าย')} {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')}"]
            for _, row in df.iterrows():
                extra = f" ({row['category']})" if row["category"] != "-" else ""
                reply.append(f"- {row['item']}: {row['amount']:,.0f} บาท{extra}")
            reply.append(f"\n📌 รวม: {total:,.0f} บาท")
            reply_text(reply_token, "\n".join(reply))
            return "OK", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายได้ 1-7/06/2025")
            return "invalid range", 200

    # --- PARSE RECORD ---
    lines = msg.strip().split("\n")
    records = []
    is_income_format = any("รายได้รวม" in l for l in lines)
    date_line = None

    for line in lines:
        if line.startswith("รายวันที่"):
            try:
                date_line = datetime.strptime(line.split(" ")[1], "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                pass

    date_str = date_line or today_str
    for line in lines:
        try:
            if "รายได้รวม" in line:
                item = "รายได้รวม"
                amount = float(line.split()[1].replace(",", ""))
                records.append((user_id, item, amount, "-", "income", date_str))
            elif any(k in line for k in ["รายได้อาหาร", "รายได้เครื่องดื่ม"]):
                parts = line.split()
                item = parts[0]
                amount = float(parts[1].replace(",", ""))
                cat = item.replace("รายได้", "")
                records.append((user_id, item, amount, cat, "income", date_str))
            elif "แยกรายได้" in line:
                parts = line.split()
                item = parts[1]
                amount = float(parts[2].replace(",", ""))
                records.append((user_id, f"แยกรายได้: {item}", amount, item, "income", date_str))
            else:
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    item, amount = parts
                    amount = float(amount.replace(",", ""))
                    parts2 = item.rsplit(" ", 1)
                    if len(parts2) == 2:
                        item, cat = parts2
                    else:
                        cat = "-"
                    records.append((user_id, item.strip(), amount, cat.strip(), "expense", today_str))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายได้รวม 13000 หรือ ค่าน้ำ 50 ของใช้")
        return "format error", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()

    df = pd.read_sql_query("SELECT * FROM records WHERE user_id=?", conn, params=(user_id,))
    df["date"] = pd.to_datetime(df["date"])
    today_df = df[df["date"] == pd.to_datetime(today_str)]
    month_df = df[df["date"].dt.to_period("M") == today.strftime("%Y-%m")]

    income_today = today_df[today_df["type"] == "income"]
    expense_today = today_df[today_df["type"] == "expense"]
    total_income = income_today["amount"].sum()
    total_expense = expense_today["amount"].sum()

    lines = []
    if not income_today.empty:
        lines.append(f"📅 รายได้วันนี้ ({today_display})")
        for _, row in income_today.iterrows():
            lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท")
        lines.append(f"\n💰 รวมวันนี้: {total_income:,.0f} บาท")
        lines.append(f"🗓 รวมเดือนนี้: {month_df[month_df['type']=='income']['amount'].sum():,.0f} บาท")

    if not expense_today.empty:
        lines.append(f"📅 รายจ่ายวันนี้ ({today_display})")
        for _, row in expense_today.iterrows():
            if row["category"] != "-":
                lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท ({row['category']})")
            else:
                lines.append(f"- {row['item']}: {row['amount']:,.0f} บาท")
        lines.append(f"\n📌 รวมวันนี้: {total_expense:,.0f} บาท")
        lines.append(f"📅 รวมเดือนนี้: {month_df[month_df['type']=='expense']['amount'].sum():,.0f} บาท")

    reply_text(reply_token, "\n".join(lines))
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
