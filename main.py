from flask import Flask
import os

app = Flask(__name__)


@app.route("/")
def index():
    return "✅ LINE Expense Bot is running!"


@app.route("/run-report")
def run_report():
    os.system("python3 weekly_report.py")
    return "✅ Report triggered", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
