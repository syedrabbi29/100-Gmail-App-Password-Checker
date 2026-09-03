import imaplib
from flask import Flask, jsonify, render_template, request

# template_folder='.' দিলে index.html সরাসরি একই ফোল্ডারে রাখা যায়
app = Flask(__name__, template_folder=".")


def verify_account(email, app_password):
    try:
        cleaned_pass = app_password.strip().replace(" ", "")
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email.strip(), cleaned_pass)
        mail.logout()
        return True
    except Exception:
        return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/check-single", methods=["POST"])
def check_single():
    data = request.json or {}
    email = data.get("email", "")
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"status": "error", "message": "তথ্য অসম্পূর্ণ"}), 400

    is_valid = verify_account(email, password)
    return jsonify(
        {
            "status": "success" if is_valid else "failed",
            "email": email,
            "isValid": is_valid,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
