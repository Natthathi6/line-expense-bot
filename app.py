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
    user_map = {
        "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
        "U542df4ce137fedb29062de182f47a27f": "Eye" ,
        "U2ba8c45280334de1674d1e3aae772289": "Tiger" 
    }
    return user_map.get(user_id, user_id)

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
        ws1.append(["วันที่", "ผู้ใช้", "รายได้รวม (บาท)"])

        df = pd.DataFrame(rows, columns=["user_id", "item", "amount", "category", "type", "date"])
        df = df[df["type"] == "income"]
        df["date"] = pd.to_datetime(df["date"])
        df["date_str"] = df["date"].dt.strftime("%d-%m-%Y")

        grouped = df.groupby(["date_str", "user_id"])["amount"].sum().reset_index()
        for _, row in grouped.iterrows():
            ws1.append([row["date_str"], get_user_name(row["user_id"]), f"{row['amount']:,.0f}"])

        ws2 = wb.create_sheet(title="Expense")
        ws2.append(["User", "Item", "Amount", "Category", "Date"])
        for r in rows:
            if r[4] == "expense":
                ws2.append([get_user_name(r[0]), r[1], r[2], r[3], datetime.strptime(r[5], "%Y-%m-%d").strftime("%d-%m-%Y")])

        file_path = "records_export.xlsx"
        wb.save(file_path)
        reply_text(reply_token, f"📥 ไฟล์ export เสร็จแล้ว ดาวน์โหลดได้ที่:\nhttps://{request.host}/records_export.xlsx")
        return "export ok", 200

    # ลบข้อมูลตามช่วงวัน
    for keyword, ttype in [("ลบรายได้", "income"), ("ลบรายจ่าย", "expense")]:
        if msg.lower().startswith(keyword):
            try:
                range_str = msg[len(keyword):].strip()
                if "-" in range_str:
                    d1_str, d2_str = range_str.split("-")
                    d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
                    d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
                else:
                    d1 = d2 = datetime.strptime(range_str.strip(), "%d %b %Y")
                conn.execute("DELETE FROM records WHERE user_id=? AND type=? AND date BETWEEN ? AND ?",
                             (user_id, ttype, d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d")))
                conn.commit()
                reply_text(reply_token, f"🧹 ลบ{ttype} {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')} แล้ว")
                return "deleted", 200
            except:
                reply_text(reply_token, f"❌ รูปแบบผิด เช่น: {keyword} 5 Jun 2025 หรือ {keyword} 1 Jun 2025 - 10 Jun 2025")
                return "invalid del", 200

    # รวมรายได้/รายจ่าย พร้อมแยกรายได้แบบใหม่
    if msg.lower().startswith("รวมรายได้"):
        try:
            _, range_str = msg.split("รวมรายได้")
            d1_str, d2_str = range_str.strip().split("-")
            d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
            d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
            df = pd.read_sql_query(f"SELECT * FROM records WHERE type='income'", conn)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= d1) & (df["date"] <= d2)]
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
            sum_channel = summary["โอน"] + summary["เงินสด"] + summary["เครดิต"]
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

    # รวมรายจ่ายแบบแจกแจงรายการ
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
            reply = [f"💸 รวมรายจ่าย {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}: {total:,.0f} บาท"]
            grouped = df.groupby("date")
            for day, rows in grouped:
                reply.append(f"\n📅 {day.strftime('%d/%m/%Y')}")
                for _, r in rows.iterrows():
                    if r["category"] != "-":
                        reply.append(f"- {r['item']}: {r['amount']:,.0f} บาท ({r['category']})")
                    else:
                        reply.append(f"- {r['item']}: {r['amount']:,.0f} บาท")
            reply_text(reply_token, "\n".join(reply))
            return "sum expense detail ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายจ่าย 1 Jun 2025 - 10 Jun 2025")
            return "invalid", 200

 # รายได้ประจำวันที่แยกรายการ
    if msg.startswith("รายได้วันที่"):
        try:
            lines = msg.strip().split("\n")
            date_str = lines[0].replace("รายได้วันที่", "").strip()
            date_obj = datetime.strptime(date_str, "%d %b %Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
            summary = {"อาหาร": 0, "เครื่องดื่ม": 0, "โอน": 0, "เงินสด": 0, "เครดิต": 0}
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
            sum_category = summary["อาหาร"] + summary["เครื่องดื่ม"]
            sum_channel = summary["โอน"] + summary["เงินสด"] + summary["เครดิต"]
            if sum_category != sum_channel:
                reply_text(reply_token, f"❌ ยอดรวมหมวดหมู่ไม่เท่ากับช่องทาง\nอาหาร+เครื่องดื่ม = {sum_category:,.0f}\nโอน+เงินสด+เครดิต = {sum_channel:,.0f}")
                return "mismatch", 200
            if records:
                conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
                conn.commit()
                reply = [
                    f"📅 บันทึกวันที่ {date_obj.strftime('%d-%m-%Y')}",
                    f"💵 รายได้รวม: {sum_category:,.0f} บาท",
                    f"🍟 รายได้อาหาร: {summary['อาหาร']:,.0f} บาท",
                    f"🍺 รายได้เครื่องดื่ม: {summary['เครื่องดื่ม']:,.0f} บาท",
                    "",
                    f"📌 โอน: {summary['โอน']:,.0f} บาท",
                    f"📌 เงินสด: {summary['เงินสด']:,.0f} บาท",
                    f"📌 เครดิต: {summary['เครดิต']:,.0f} บาท"
                ]
                reply_text(reply_token, "\n".join(reply))
                return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายได้วันที่ 1 Jun 2025")
            return "invalid", 200

        # รายจ่ายระบุวันที่ เช่น "รายจ่ายวันที่ 1 Jun 2025\nกาแฟ 60 เครื่องดื่ม"
    if msg.startswith("รายจ่ายวันที่"):
        try:
            lines = msg.strip().split("\n")
            date_str = lines[0].replace("รายจ่ายวันที่", "").strip()
            date_obj = datetime.strptime(date_str, "%d %b %Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
            date_display = date_obj.strftime("%d-%m-%Y")
            records = []
            for line in lines[1:]:
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
                    records.append((user_id, item.strip(), amount, category.strip(), "expense", date_iso))
                except:
                    continue
            if records:
                conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", records)
                conn.commit()
                df = pd.read_sql_query("SELECT item, amount, category FROM records WHERE user_id=? AND date=? AND type='expense'", conn, params=(user_id, date_iso))
                total = df["amount"].sum()
                reply = [f"📅 รายจ่ายวันที่ {date_display}"]
                for _, row in df.iterrows():
                    if row["category"] != "-":
                        reply.append(f"- {row['item']}: {row['amount']:,.0f} บาท ({row['category']})")
                    else:
                        reply.append(f"- {row['item']}: {row['amount']:,.0f} บาท")
                reply.append(f"\n💸 รวมวันนี้: {total:,.0f} บาท")
                reply_text(reply_token, "\n".join(reply))
                return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายจ่ายวันที่ 1 Jun 2025\\nกาแฟ 60 เครื่องดื่ม")
            return "invalid", 200

    # รายจ่ายทั่วไป (ไม่มีระบุวัน ใช้วันนี้)
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
            records.append((user_id, item.strip(), amount, category.strip(), "expense", today_str))
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
