import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import os

# --- ตั้งค่า ---
DB_PATH = "expenses.db"
USER_MAP = {
    "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
    "U8a82b2393123c38a238144698e8fd19b": "Pupae"
}

# --- เชื่อมต่อและดึงข้อมูล ---
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM expenses", conn)
conn.close()

# --- แปลง user_id เป็นชื่อ ---
df["user_id"] = df["user_id"].replace(USER_MAP)

# --- แปลงวันที่เป็น datetime ---
df["date"] = pd.to_datetime(df["date"])

# --- ดึงเฉพาะเดือนล่าสุด ---
latest_month = df["date"].dt.to_period("M").max()
df = df[df["date"].dt.to_period("M") == latest_month]

# --- ฟังก์ชันแบ่งสัปดาห์ ---
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

# --- วนลูปราย user แล้วสร้างรายงานแยก ---
for user in df["user_id"].unique():
    df_user = df[df["user_id"] == user]

    # สรุปยอดรายสัปดาห์
    summary = df_user.groupby("week")["amount"].sum().reindex(
        ["Week 1 (1-7)", "Week 2 (8-14)", "Week 3 (15-21)", "Week 4 (22-end)"],
        fill_value=0)

    # สร้างไฟล์ Excel
    excel_name = f"{user}_weekly_report.xlsx"
    df_user.to_excel(excel_name, index=False)
    print(f"✅ บันทึก Excel: {excel_name}")

    # สร้างกราฟ
    plt.figure(figsize=(8, 5))
    summary.plot(kind="bar", color="skyblue", edgecolor="black")
    plt.title(f"รายจ่าย {user} - {latest_month.strftime('%B %Y')}")
    plt.ylabel("บาท")
    plt.xticks(rotation=0)
    plt.tight_layout()
    graph_name = f"{user}_weekly_chart.png"
    plt.savefig(graph_name)
    print(f"📊 บันทึกกราฟ: {graph_name}")
    plt.close()
