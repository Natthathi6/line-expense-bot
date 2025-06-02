from flask import Flask, request
import os, sqlite3
from datetime import datetime
import pandas as pd

app = Flask(__name__)
DB_PATH = "expenses.db"
USER_MAP = {
    "Uf2299afc5c6a03b031ac70eefc750259": "Choy",
    "U8a82b2393123c38a238144698e8fd19b": "Pupae"
}

@app.route("/export-excel")
def export_excel():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM expenses", conn)
    conn.close()

    # แปลงชื่อ user
    df["user_id"] = df["user_id"].replace(USER_MAP)
    # แปลงวันที่
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%d-%m-%Y")

    filename = "expenses_exported.xlsx"
    df.to_excel(filename, index=False)

    return f"✅ Exported: {filename}", 200

@app.route("/clear", methods=["POST"])
def clear_by_date():
    try:
        text = request.args.get("text") or ""
        if not text.lower().startswith("clear"):
            return "❌ ใส่ format: clear dd-mm-yyyy", 400
        date_str = text[6:].strip()  # เช่น clear 02-06-2025
        clear_date = datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM expenses WHERE date = ?", (clear_date,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()

        return f"🧹 ลบข้อมูลวันที่ {date_str} จำนวน {deleted} รายการแล้ว", 200
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
