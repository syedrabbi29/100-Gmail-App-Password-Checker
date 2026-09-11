import imaplib
import threading
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__, template_folder=".")

# গ্লোবাল স্টেট (ব্যাকগ্রাউন্ড ডাটা সংরক্ষণ করার জন্য)
task_state = {
    "is_running": False,
    "total": 0,
    "checked": 0,
    "success_count": 0,
    "failed_count": 0,
    "success_list": [],  # ['email : pass', ...]
    "failed_list": [],  # ['email : pass', ...]
    "logs": [],  # লাইভ লগ মেসেজ
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


def background_worker(email_pass_pairs):
    global task_state

    with state_lock:
        task_state["is_running"] = True
        task_state["stop_requested"] = False
        task_state["total"] = len(email_pass_pairs)
        task_state["checked"] = 0
        task_state["success_count"] = 0
        task_state["failed_count"] = 0
        task_state["success_list"] = []
        task_state["failed_list"] = []
        task_state["logs"] = ["ব্যাকগ্রাউন্ড চেকিং শুরু হয়েছে..."]

    for idx, (email, pwd) in enumerate(email_pass_pairs):
        # ইউজার যদি Stop বাটনে ক্লিক করে
        if task_state["stop_requested"]:
            with state_lock:
                task_state["logs"].append("⛔ ব্যবহারকারী চেকিং বন্ধ করেছেন!")
            break

        # চেক করা
        is_valid = verify_account(email, pwd)

        with state_lock:
            task_state["checked"] = idx + 1
            pair_str = f"{email}:{pwd}"
            if is_valid:
                task_state["success_count"] += 1
                task_state["success_list"].append(pair_str)
                task_state["logs"].append(f"[{idx+1}] ✅ Success: {email}")
            else:
                task_state["failed_count"] += 1
                task_state["failed_list"].append(pair_str)
                task_state["logs"].append(f"[{idx+1}] ❌ Failed: {email}")

            # লগ লিস্ট খুব বেশি বড় যেন না হয় (সর্বশেষ ১০০টি রাখবে)
            if len(task_state["logs"]) > 100:
                task_state["logs"].pop(0)

        # শেষ অ্যাকাউন্টের পর অপ্রয়োজনীয় বিরতি না দেওয়া
        if idx < len(email_pass_pairs) - 1:
            # ৩০ সেকেন্ডের স্লিপ (প্রতি সেকেন্ডে চেক করবে Stop চাপলো কিনা)
            for _ in range(30):
                if task_state["stop_requested"]:
                    break
                time.sleep(1)

    with state_lock:
        task_state["is_running"] = False
        if not task_state["stop_requested"]:
            task_state["logs"].append("🎉 সব অ্যাকাউন্ট চেক করা সম্পন্ন হয়েছে!")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_check():
    global task_state
    if task_state["is_running"]:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "ইতিমধ্যে একটি টাস্ক ব্যাকগ্রাউন্ডে চলছে!",
                }
            ),
            400,
        )

    data = request.json or {}
    emails = [
        e.strip()
        for e in data.get("emails", "").strip().split("\n")
        if e.strip()
    ]
    passwords = [
        p.strip()
        for p in data.get("passwords", "").strip().split("\n")
        if p.strip()
    ]

    if not emails or not passwords:
        return (
            jsonify({"status": "error", "message": "উভয় বক্সে তথ্য দিন!"}),
            400,
        )

    if len(emails) != len(passwords):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"ইমেইল ({len(emails)}) এবং পাসওয়ার্ডের ({len(passwords)}) সংখ্যা সমান নয়!",
                }
            ),
            400,
        )

    pairs = list(zip(emails, passwords))

    # ব্যাকগ্রাউন্ড থ্রেড রান করা
    thread = threading.Thread(
        target=background_worker, args=(pairs,), daemon=True
    )
    thread.start()

    return jsonify({"status": "success", "message": "চেকিং শুরু হয়েছে!"})


@app.route("/stop", methods=["POST"])
def stop_check():
    global task_state
    if task_state["is_running"]:
        task_state["stop_requested"] = True
        return jsonify(
            {"status": "success", "message": "টাস্ক থামানোর নির্দেশ দেওয়া হয়েছে"}
        )
    return jsonify({"status": "error", "message": "কোনো টাস্ক চলছে না"})


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
