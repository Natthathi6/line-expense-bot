import sqlite3
import pandas as pd
from datetime import datetime
import requests
import os

# เช็กว่าวันนี้ตรงกับวันที่ต้องรายงานอัตโนมัติหรือไม่
today = datetime.today().day
if today not in [8, 15, 22, 1]:
    print("⏱ ไม่ใช่วันรายงานอัตโนมัติ")
    exit()

# --- ตั้งค่า ---
DB_PATH = "runtime.db"
LINE_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
USER_MAP = {
    "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
    "U8a82b2393123c38a238144698e8fd19b": "Pupae"
}

# --- โหลดข้อมูล ---
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM expenses", conn)
conn.close()

df["date"] = pd.to_datetime(df["date"])
latest_month = df["date"].dt.to_period("M").max()
df = df[df["date"].dt.to_period("M") == latest_month]

# --- แบ่งสัปดาห์ ---
def classify_week(d):
    day = d.day
    if day <= 7:
        return "Week 1 (1-7)"
    elif day <= 14:
        return "Week 2 (8-14)"
    elif day <= 21:
        return "Week 3 (15-21)"
    else:
        return "Week 4 (22-end)"

df["week"] = df["date"].apply(classify_week)

# --- ส่งรายงานราย user ---
for user_id, name in USER_MAP.items():
    df_user = df[df["user_id"] == user_id]
    if df_user.empty:
        continue

    summary = df_user.groupby("week")["amount"].sum()
    total = df_user["amount"].sum()

    text_lines = [f"📊 รายจ่ายเดือน {latest_month.strftime('%B %Y')} ของ {name}"]

    for week in ["Week 1 (1-7)", "Week 2 (8-14)", "Week 3 (15-21)", "Week 4 (22-end)"]:
        baht = summary.get(week, 0)
        text_lines.append(f"• {week}: {baht:,.0f} บาท")

        # เพิ่ม: แยกหมวดในแต่ละสัปดาห์
        df_week = df_user[df_user["week"] == week]
        cat_summary = df_week.groupby("category")["amount"].sum().sort_values(ascending=False)
        for cat, amt in cat_summary.items():
            text_lines.append(f"    - {cat}: {amt:,.0f} บาท")

    text_lines.append(f"\n💰 รวมทั้งเดือน: {total:,.0f} บาท")

    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": "\n".join(text_lines)}]
    }
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
