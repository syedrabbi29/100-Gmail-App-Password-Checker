import imaplib
import re
import threading
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__, template_folder=".")

task_state = {
    "is_running": False,
    "total": 0,
    "checked": 0,
    "success_count": 0,
    "failed_count": 0,
    "success_list": [],
    "failed_list": [],
    "logs": [],
    "stop_requested": False,
}

state_lock = threading.Lock()


def verify_account(email, app_password):
    try:
        cleaned_pass = app_password.strip().replace(" ", "")
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email.strip(), cleaned_pass)
        mail.logout()
        return True
    except Exception:
        return False


def parse_line(line):
    parts = re.split(r"[\t, ]+", line.strip())
    if len(parts) >= 2:
        email = parts[0]
        app_password = parts[-1]
        return email, app_password
    return None, None


def background_worker(data_lines):
    global task_state

    with state_lock:
        task_state["is_running"] = True
        task_state["stop_requested"] = False
        task_state["total"] = len(data_lines)
        task_state["checked"] = 0
        task_state["success_count"] = 0
        task_state["failed_count"] = 0
        task_state["success_list"] = []
        task_state["failed_list"] = []
        task_state["logs"] = ["চেকিং শুরু হয়েছে..."]

    for idx, raw_line in enumerate(data_lines):
        if task_state["stop_requested"]:
            with state_lock:
                task_state["logs"].append("⛔ ইউজার প্রসেস বন্ধ করেছেন!")
            break

        email, app_pwd = parse_line(raw_line)

        if not email or not app_pwd:
            with state_lock:
                task_state["checked"] = idx + 1
                task_state["failed_count"] += 1
                task_state["failed_list"].append(raw_line)
                task_state["logs"].append(f"[{idx+1}] ❌ Invalid Line Format")
            continue

        is_valid = verify_account(email, app_pwd)

        with state_lock:
            task_state["checked"] = idx + 1
            if is_valid:
                task_state["success_count"] += 1
                task_state["success_list"].append(raw_line)
                task_state["logs"].append(f"[{idx+1}] ✅ Success: {email}")
            else:
                task_state["failed_count"] += 1
                task_state["failed_list"].append(raw_line)
                task_state["logs"].append(f"[{idx+1}] ❌ Failed: {email}")

            if len(task_state["logs"]) > 100:
                task_state["logs"].pop(0)

        if idx < len(data_lines) - 1:
            for _ in range(30):
                if task_state["stop_requested"]:
                    break
                time.sleep(1)

    with state_lock:
        task_state["is_running"] = False
        if not task_state["stop_requested"]:
            task_state["logs"].append("🎉 সব অ্যাকাউন্ট চেক করা শেষ!")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_check():
    global task_state
    if task_state["is_running"]:
        return (
            jsonify(
                {"status": "error", "message": "ইতিমধ্যে চেকিং চালু রয়েছে!"}
            ),
            400,
        )

    data = request.json or {}
    raw_text = data.get("data", "").strip()

    if not raw_text:
        return (
            jsonify({"status": "error", "message": "কোনো ডেটা দেওয়া হয়নি!"}),
            400,
        )

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    thread = threading.Thread(
        target=background_worker, args=(lines,), daemon=True
    )
    thread.start()

    return jsonify({"status": "success", "message": "টাস্ক শুরু হয়েছে!"})


@app.route("/stop", methods=["POST"])
def stop_check():
    global task_state
    if task_state["is_running"]:
        task_state["stop_requested"] = True
        return jsonify({"status": "success", "message": "থামানো হচ্ছে..."})
    return jsonify({"status": "error", "message": "কোনো চেকিং চলছে না"})


@app.route("/clear", methods=["POST"])
def clear_state():
    global task_state
    if task_state["is_running"]:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "চেকিং চলাকালীন ডেটা ক্লিয়ার করা যাবে না! আগে Stop করুন।",
                }
            ),
            400,
        )

    with state_lock:
        task_state["total"] = 0
        task_state["checked"] = 0
        task_state["success_count"] = 0
        task_state["failed_count"] = 0
        task_state["success_list"] = []
        task_state["failed_list"] = []
        task_state["logs"] = []

    return jsonify(
        {"status": "success", "message": "সব ডেটা সম্পূর্ণ ক্লিয়ার করা হয়েছে!"}
    )


@app.route("/status", methods=["GET"])
def get_status():
    with state_lock:
        return jsonify(
            {
                "isRunning": task_state["is_running"],
                "total": task_state["total"],
                "checked": task_state["checked"],
                "successCount": task_state["success_count"],
                "failedCount": task_state["failed_count"],
                "successList": task_state["success_list"],
                "failedList": task_state["failed_list"],
                "logs": task_state["logs"],
            }
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
