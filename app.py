from flask import Flask, request, send_file
import os
from datetime import datetime
import requests
from openpyxl import Workbook
import pandas as pd

# === Supabase config ===
SUPABASE_URL = "https://gehcembieoaterpjoftt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def insert_record(user_id, item, amount, category, type_, date_str):
    url = f"{SUPABASE_URL}/rest/v1/records"
    payload = {
        "user_id": user_id,
        "item": item,
        "amount": amount,
        "category": category,
        "type": type_,
        "date": date_str
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    return r.status_code == 201

def fetch_records(user_id, type_, start_date, end_date):
    url = f"{SUPABASE_URL}/rest/v1/records?user_id=eq.{user_id}&type=eq.{type_}&date=gte.{start_date}&date=lte.{end_date}&order=date.asc"
    r = requests.get(url, headers=HEADERS)
    return r.json() if r.status_code == 200 else []

def delete_records(user_id, type_, start_date, end_date):
    url = f"{SUPABASE_URL}/rest/v1/records?user_id=eq.{user_id}&type=eq.{type_}&date=gte.{start_date}&date=lte.{end_date}"
    r = requests.delete(url, headers=HEADERS)
    return r.status_code == 204

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
    url = f"{SUPABASE_URL}/rest/v1/records?select=*"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return "Error fetching records from Supabase", 500
    data = r.json()
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Income"
    ws1.append(["User", "Item", "Amount", "Category", "Date"])
    for row in data:
        if row["type"] == "income":
            ws1.append([get_user_name(row["user_id"]), row["item"], row["amount"], row["category"], row["date"]])
    ws2 = wb.create_sheet(title="Expense")
    ws2.append(["User", "Item", "Amount", "Category", "Date"])
    for row in data:
        if row["type"] == "expense":
            ws2.append([get_user_name(row["user_id"]), row["item"], row["amount"], row["category"], row["date"]])
    file_path = "records_export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

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

    if msg.lower().strip() == "export":
        reply_text(reply_token, f"📥 ไฟล์ export เสร็จแล้ว ดาวน์โหลดได้ที่:\nhttps://{request.host}/records_export.xlsx")
        return "export ok", 200

    if msg.lower().startswith("รวมรายจ่าย"):
        try:
            _, range_str = msg.split("รวมรายจ่าย")
            d1_str, d2_str = range_str.strip().split("-")
            d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
            d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
            records = fetch_records(user_id, "expense", d1.strftime('%Y-%m-%d'), d2.strftime('%Y-%m-%d'))
            if not records:
                reply_text(reply_token, f"📍 ไม่มีรายจ่ายในช่วงที่ระบุ")
                return "no data", 200
            total = sum(r["amount"] for r in records)
            reply = [f"💸 รวมรายจ่าย {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')}: {total:,.0f} บาท"]
            current_date = ""
            for r in records:
                if r["date"] != current_date:
                    current_date = r["date"]
                    reply.append(f"\n📅 {datetime.strptime(current_date, '%Y-%m-%d').strftime('%d/%m/%Y')}")
                if r["category"] != "-":
                    reply.append(f"- {r['item']}: {r['amount']:,.0f} บาท ({r['category']})")
                else:
                    reply.append(f"- {r['item']}: {r['amount']:,.0f} บาท")
            reply_text(reply_token, "\n".join(reply))
            return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายจ่าย 1 Jun 2025 - 10 Jun 2025")
            return "invalid", 200

    if msg.lower().startswith("รวมรายได้"):
        try:
            _, range_str = msg.split("รวมรายได้")
            d1_str, d2_str = range_str.strip().split("-")
            d1 = datetime.strptime(d1_str.strip(), "%d %b %Y")
            d2 = datetime.strptime(d2_str.strip(), "%d %b %Y")
            records = fetch_records(user_id, "income", d1.strftime('%Y-%m-%d'), d2.strftime('%Y-%m-%d'))
            if not records:
                reply_text(reply_token, f"📍 ไม่มีรายได้ในช่วงที่ระบุ")
                return "no data", 200
            summary = {"อาหาร": 0, "เครื่องดื่ม": 0, "โอน": 0, "เงินสด": 0, "เครดิต": 0}
            for r in records:
                if r["category"] in summary:
                    summary[r["category"]] += r["amount"]
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
            return "ok", 200
        except:
            reply_text(reply_token, "❌ รูปแบบผิด เช่น: รวมรายได้ 1 Jun 2025 - 10 Jun 2025")
            return "invalid", 200

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
                deleted = delete_records(user_id, ttype, d1.strftime('%Y-%m-%d'), d2.strftime('%Y-%m-%d'))
                if deleted:
                    reply_text(reply_token, f"🧹 ลบ{ttype} {d1.strftime('%d/%m')} - {d2.strftime('%d/%m')} แล้ว")
                else:
                    reply_text(reply_token, f"❌ ลบ{ttype} ไม่สำเร็จ")
                return "deleted", 200
            except:
                reply_text(reply_token, f"❌ รูปแบบผิด เช่น: {keyword} 5 Jun 2025 หรือ {keyword} 1 Jun 2025 - 10 Jun 2025")
                return "invalid del", 200

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
