# ✅ LINE Income & Expense Bot: Full Feature Version

from flask import Flask, request, send_file
import os
import sqlite3
from datetime import datetime
from openpyxl import Workbook
import pandas as pd
import requests

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
    return "✅ LINE Bot Ready"

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

    # === EXPORT ===
    if msg.strip().lower() == "export":
        df = pd.read_sql_query("SELECT * FROM records", conn)
        wb = Workbook()
        ws_income = wb.active
        ws_income.title = "Income"
        ws_income.append(["User", "Item", "Amount", "Category", "Date"])
        for r in df[df.type == 'income'].itertuples():
            ws_income.append([get_user_name(r.user_id), r.item, r.amount, r.category, r.date])

        ws_exp = wb.create_sheet("Expense")
        ws_exp.append(["User", "Item", "Amount", "Category", "Date"])
        for r in df[df.type == 'expense'].itertuples():
            ws_exp.append([get_user_name(r.user_id), r.item, r.amount, r.category, r.date])

        file_path = "records_export.xlsx"
        wb.save(file_path)
        conn.close()
        return send_file(file_path, as_attachment=True)

    # === DELETE ===
    if msg.lower().startswith("ลบรายได้"):
        try:
            d = datetime.strptime(msg[9:].strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND type='income' AND date=?", (user_id, d))
            conn.commit()
            reply_text(reply_token, f"🗑 ลบรายได้วันที่ {d} แล้ว")
            return "OK", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: ลบรายได้ 01-06-2025")
            return "ERR", 200

    if msg.lower().startswith("ลบรายจ่าย"):
        try:
            d = datetime.strptime(msg[10:].strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
            conn.execute("DELETE FROM records WHERE user_id=? AND type='expense' AND date=?", (user_id, d))
            conn.commit()
            reply_text(reply_token, f"🗑 ลบรายจ่ายวันที่ {d} แล้ว")
            return "OK", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: ลบรายจ่าย 01-06-2025")
            return "ERR", 200

    # === รวมตามช่วงวันที่ ===
    if msg.startswith("รวมรายได้"):
        try:
            date_range = msg[10:].strip().replace(" ", "")
            d1, d2 = date_range.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records WHERE type='income'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, "❌ ไม่มีรายได้ในช่วงนี้")
                return "NO", 200
            total = df["amount"].sum()
            lines = [f"📊 รวมรายได้ {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')}"]
            for _, r in df.iterrows():
                lines.append(f"- {r.item}: {int(r.amount) if r.amount.is_integer() else r.amount:,} บาท")
            lines.append(f"\n💰 รวมรายได้: {int(total) if total.is_integer() else total:,} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "OK", 200
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รวมรายได้ 1-7/06/2025")
            return "ERR", 200

    if msg.startswith("รวมรายจ่าย"):
        try:
            date_range = msg[11:].strip().replace(" ", "")
            d1, d2 = date_range.split("-")
            d1 = datetime.strptime(d1 + "/2025", "%d/%m/%Y")
            d2 = datetime.strptime(d2 + "/2025", "%d/%m/%Y")
            df = pd.read_sql_query("SELECT * FROM records WHERE type='expense'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["user_id"] == user_id) & (df["date"] >= d1) & (df["date"] <= d2)]
            if df.empty:
                reply_text(reply_token, "❌ ไม่มีรายจ่ายในช่วงนี้")
                return "NO", 200
            total = df["amount"].sum()
            lines = [f"📊 รวมรายจ่าย {d1.strftime('%d/%m')}–{d2.strftime('%d/%m')}"]
            for _, r in df.iterrows():
                detail = f" ({r.category})" if r.category != "-" else ""
                lines.append(f"- {r.item}: {int(r.amount) if r.amount.is_integer() else r.amount:,} บาท{detail}")
            lines.append(f"\n💸 รวมรายจ่าย: {int(total) if total.is_integer() else total:,} บาท")
            reply_text(reply_token, "\n".join(lines))
            return "OK", 200
        except:
            reply_text(reply_token, "❌ รูปแบบไม่ถูกต้อง เช่น: รวมรายจ่าย 1-7/06/2025")
            return "ERR", 200

    # === บันทึกข้อมูล ===
    lines = msg.strip().split("\n")
    records = []
    current_date = today_str
    for line in lines:
        if line.startswith("รายวันที่"):
            try:
                current_date = datetime.strptime(line.split("วันที่")[-1].strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                current_date = today_str
            continue
        try:
            parts = line.strip().split()
            if len(parts) >= 2:
                item = " ".join(parts[:-1])
                amt = float(parts[-1].replace(",", ""))
                if item.startswith("รายได้") or item.startswith("แยกรายได้"):
                    records.append((user_id, item, amt, "-", "income", current_date))
                else:
                    category = parts[-1] if len(parts) >= 3 else "-"
                    item = " ".join(parts[:-2]) if len(parts) >= 3 else " ".join(parts[:-1])
                    records.append((user_id, item.strip(), amt, category.strip(), "expense", current_date))
        except:
            continue

    if not records:
        reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายได้รวม 13000 หรือ ค่าน้ำ 50 ของใช้")
        return "BAD", 200

    conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    df = pd.DataFrame(records, columns=["user_id", "item", "amount", "category", "type", "date"])

    if all(df.type == 'income'):
        today_display = datetime.strptime(current_date, "%Y-%m-%d").strftime("%d-%m-%Y")
        summary = df.groupby("item")["amount"].sum()
        lines = [f"📅 บันทึกวันที่ {today_display}"]
        icon_map = {
            "รายได้รวม": "💵", "รายได้อาหาร": "🍟", "รายได้เครื่องดื่ม": "🍺",
            "แยกรายได้โอน": "📌", "แยกรายได้เงินสด": "📌", "แยกรายได้เครดิต": "📌"
        }
        for key, val in summary.items():
            icon = icon_map.get(key.split()[0] + key.split()[1], "-")
            lines.append(f"{icon} {key}: {int(val) if val.is_integer() else val:,} บาท")
        reply_text(reply_token, "\n\n".join("\n".join(lines).split("\n📌", 1)))
        return "OK", 200

    else:
        # รายจ่าย
        df_today = pd.read_sql_query("SELECT item, amount, category FROM records WHERE user_id=? AND date=? AND type='expense'", conn, params=(user_id, current_date))
        total = df_today["amount"].sum()
        month = current_date[:7] + "%"
        month_total = conn.execute("SELECT SUM(amount) FROM records WHERE user_id=? AND type='expense' AND date LIKE ?", (user_id, month)).fetchone()[0] or 0

        lines = [f"📅 รายจ่ายวันนี้ ({datetime.strptime(current_date, '%Y-%m-%d').strftime('%d-%m-%Y')})"]
        for _, r in df_today.iterrows():
            detail = f" ({r['category']})" if r['category'] != "-" else ""
            lines.append(f"- {r['item']}: {int(r['amount']) if r['amount'].is_integer() else r['amount']:,} บาท{detail}")
        lines.append(f"\n📌 รวมวันนี้: {int(total) if total.is_integer() else total:,} บาท")
        lines.append(f"🗓 รวมเดือนนี้: {int(month_total) if month_total.is_integer() else month_total:,} บาท")
        reply_text(reply_token, "\n".join(lines))
        return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
