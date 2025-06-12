from flask import Flask, request, send_file
import os
import requests
from datetime import datetime
from openpyxl import Workbook
import pandas as pd

app = Flask(__name__)
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
SUPABASE_URL = "https://gehcembieoaterpjoftt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def get_user_name(user_id):
    return {
        "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
        "U8a82b2393123c38a238144698e8fd19b": "Pupae"
    }.get(user_id, "คุณ")

def reply_text(reply_token, text):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            'Authorization': f'Bearer {LINE_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'replyToken': reply_token,
            'messages': [{'type': 'text', 'text': text}]
        }
    )

def insert_record(user_id, item, amount, category, type_, date):
    url = f"{SUPABASE_URL}/rest/v1/records"
    payload = {
        "user_id": user_id,
        "item": item,
        "amount": amount,
        "category": category,
        "type": type_,
        "date": date
    }
    return requests.post(url, headers=HEADERS, json=payload).ok

@app.route("/")
def index():
    return "✅ LINE Income/Expense Bot with Supabase is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        msg = data["events"][0]["message"]["text"]
        user_id = data["events"][0]["source"]["userId"]
        reply_token = data["events"][0]["replyToken"]
    except:
        return "ignored", 200

    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    today_display = today.strftime('%d-%m-%Y')

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
            records.append((user_id, item.strip(), amount, category.strip(), "expense", today_str))
        except:
            continue

    if records:
        for r in records:
            insert_record(*r)
        total_today = sum([r[2] for r in records])
        reply = [f"📅 รายจ่ายวันนี้ ({today_display})"]
        for r in records:
            if r[3] != "-":
                reply.append(f"- {r[1]}: {r[2]:,.0f} บาท ({r[3]})")
            else:
                reply.append(f"- {r[1]}: {r[2]:,.0f} บาท")
        reply.append(f"\n💸 รวมวันนี้: {total_today:,.0f} บาท")
        reply_text(reply_token, "\n".join(reply))
        return "ok", 200

    # รายได้ประจำวันที่แบบ "รายวันที่ ..."
    if msg.startswith("รายวันที่"):
        try:
            lines = msg.strip().split("\n")
            date_str = lines[0].replace("รายวันที่", "").strip()
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
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
            for r in records:
                insert_record(*r)
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
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รายวันที่ 01/06/2025")
            return "invalid", 200

    reply_text(reply_token, "❌ ไม่พบข้อมูลที่สามารถบันทึกได้")
    return "fail", 200

@app.route("/records_export.xlsx")
def download_export_file():
    url = f"{SUPABASE_URL}/rest/v1/records?select=*"
    res = requests.get(url, headers=HEADERS)
    rows = res.json() if res.ok else []

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Income"
    ws1.append(["User", "Item", "Amount", "Category", "Date"])
    for r in rows:
        if r["type"] == "income":
            ws1.append([
                get_user_name(r["user_id"]), r["item"], r["amount"], r["category"],
                datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d-%m-%Y")
            ])

    ws2 = wb.create_sheet(title="Expense")
    ws2.append(["User", "Item", "Amount", "Category", "Date"])
    for r in rows:
        if r["type"] == "expense":
            ws2.append([
                get_user_name(r["user_id"]), r["item"], r["amount"], r["category"],
                datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d-%m-%Y")
            ])

    file_path = "records_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
