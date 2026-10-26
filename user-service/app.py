import os
import secrets
import smtplib
import hashlib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode

import pymysql
import redis
from pymysql.cursors import DictCursor

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    password=os.getenv("REDIS_PASSWORD") or None,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=5,
    health_check_interval=30,
)

MAX_LOGIN_ATTEMPTS = int(os.getenv("REDIS_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("REDIS_LOGIN_WINDOW_SECONDS", "900"))
RESET_PASSWORD_TTL_SECONDS = 900

reset_link = (
    f"{PASSWORD_RESET_URL}?{urlencode({'mode': 'reset', 'email': email)}"
)
INCREMENT_LOGIN_FAILURE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def get_db():
    return pymysql.connect(
        host=app.config["DB_HOST"],
        port=app.config["DB_PORT"],
        user=app.config["DB_USER"],
        password=app.config["DB_PASSWORD"],
        database=app.config["DB_NAME"],
        cursorclass=DictCursor,
        autocommit=False,
    )


def get_login_attempt_key(identity):
    identity_hash = hashlib.sha256(
        identity.strip().lower().encode("utf-8")
    ).hexdigest()

    return f"media-tools:login-attempts:{identity_hash}"


def get_reset_password_key(email):
    email_hash = hashlib.sha256(
        email.strip().lower().encode("utf-8")
    ).hexdigest()

    return f"media-tools:password-reset:{email_hash}"


def is_login_rate_limited(key):
    attempts = redis_client.get(key)
    return attempts is not None and int(attempts) >= MAX_LOGIN_ATTEMPTS


def record_failed_login(key):
    return int(
        redis_client.eval(
            INCREMENT_LOGIN_FAILURE_SCRIPT,
            1,
            key,
            LOGIN_WINDOW_SECONDS,
        )
    )


def send_temporary_password(email, temporary_password):
    gmail_username = os.environ.get("GMAIL_USERNAME")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_username or not gmail_app_password:
        raise RuntimeError("Gmail SMTP credentials are not configured")

    reset_link = (
        f"{PASSWORD_RESET_URL}?{urlencode({
            'mode': 'reset',
            'email': email,
        })}"
    )

    message = EmailMessage()
    message["Subject"] = "Media Tools - Reset Your Password"
    message["From"] = gmail_username
    message["To"] = email

    message.set_content(
        f"""Hello,

We received a request to reset the password associated with your Media Tools account.

To securely regain access, we have generated a temporary password.

YOUR TEMPORARY PASSWORD

{temporary_password}

RESET YOUR PASSWORD

Click the link below to open the password reset form directly:

{reset_link}

Follow these steps:

1. Open the password reset link above.
2. Enter the temporary password provided in this email.
3. Enter your new password and confirm it.
4. Submit the form to complete the password reset.
5. Return to the login page and sign in using your registered username
   or email address and your new password.

IMPORTANT SECURITY INFORMATION

Your temporary password expires in 15 minutes.

It is only for resetting your password and cannot be used to log in.
After a successful reset, the temporary password is invalidated.

If your temporary password expires, request another password reset.

If you did not request this password reset, please ignore this email.
Your account password will remain unchanged unless a valid reset is
completed.

Thank you for using Media Tools.

Best regards,
Media Tools Support Team
"""
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls()
        server.login(gmail_username, gmail_app_password)
        server.send_message(message)


def initialize_database():
    connection = get_db()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        connection.commit()
    finally:
        connection.close()


initialize_database()


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/forgot-password", methods=["GET"])
def forgot_password_page():
    return send_from_directory(STATIC_DIR, "forgot-password.html")


@app.route("/static/<path:filename>", methods=["GET"])
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/health", methods=["GET"])
def health():
    try:
        redis_client.ping()

        return jsonify(
            service="user",
            status="ok",
            redis="connected",
        ), 200

    except redis.RedisError:
        app.logger.exception("Redis health check failed")

        return jsonify(
            service="user",
            status="unhealthy",
            redis="disconnected",
        ), 503


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or request.form

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not email or not password:
        return jsonify(
            error="Username, email and password are required"
        ), 400

    if len(password) < 8:
        return jsonify(
            error="Password must contain at least 8 characters"
        ), 400

    connection = get_db()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (
                    username,
                    email,
                    generate_password_hash(password),
                ),
            )

        connection.commit()

    except pymysql.err.IntegrityError:
        connection.rollback()

        return jsonify(
            error="Username or email already exists"
        ), 409

    finally:
        connection.close()

    return jsonify(message="Account created successfully"), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form

    username_or_email = str(
        data.get("username", data.get("email", ""))
    ).strip().lower()

    password = str(data.get("password", ""))

    if not username_or_email or not password:
        return jsonify(
            error="Username/email and password are required"
        ), 400

    attempt_key = get_login_attempt_key(username_or_email)

    try:
        if is_login_rate_limited(attempt_key):
            return jsonify(
                error="Too many failed login attempts. Try again later."
            ), 429

    except redis.RedisError:
        app.logger.exception("Redis login rate-limit check failed")

        return jsonify(
            error="User service temporarily unavailable"
        ), 503

    connection = get_db()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, email, password_hash
                FROM users
                WHERE LOWER(username) = %s OR LOWER(email) = %s
                """,
                (username_or_email, username_or_email),
            )

            user = cursor.fetchone()

    finally:
        connection.close()

    if user is None or not check_password_hash(
        user["password_hash"], password
    ):
        try:
            attempts = record_failed_login(attempt_key)

            if attempts >= MAX_LOGIN_ATTEMPTS:
                return jsonify(
                    error="Too many failed login attempts. Try again later."
                ), 429

        except redis.RedisError:
            app.logger.exception("Redis failed to record login attempt")

            return jsonify(
                error="User service temporarily unavailable"
            ), 503

        return jsonify(
            error="Invalid username/email or password"
        ), 401

    try:
        redis_client.delete(attempt_key)

    except redis.RedisError:
        app.logger.exception("Redis failed to clear login attempts")

        return jsonify(
            error="User service temporarily unavailable"
        ), 503

    return jsonify(
        message="Login successful",
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        },
    ), 200


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or request.form
    email = str(data.get("email", "")).strip().lower()

    if not email:
        return jsonify(error="Email is required"), 400

    reset_key = get_reset_password_key(email)
    connection = None

    try:
        connection = get_db()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE LOWER(email) = %s
                """,
                (email,),
            )

            user = cursor.fetchone()

        if user is None:
            return jsonify(
                message=(
                    "If the email is registered, a temporary password "
                    "has been sent."
                )
            ), 200

        temporary_password = secrets.token_urlsafe(24)
        temporary_password_hash = generate_password_hash(
            temporary_password
        )

        redis_client.set(
            reset_key,
            temporary_password_hash,
            ex=RESET_PASSWORD_TTL_SECONDS,
        )

        try:
            send_temporary_password(email, temporary_password)

        except Exception:
            try:
                redis_client.delete(reset_key)
            except redis.RedisError:
                app.logger.exception(
                    "Failed to remove temporary password after email failure"
                )

            raise

        return jsonify(
            message=(
                "If the email is registered, a temporary password "
                "has been sent. It expires in 15 minutes."
            )
        ), 200

    except redis.RedisError:
        app.logger.exception("Redis password-reset operation failed")

        return jsonify(
            error="Password reset service temporarily unavailable"
        ), 503

    except Exception:
        app.logger.exception("Password reset email delivery failed")

        return jsonify(
            error="Unable to send the temporary password. Please try again later."
        ), 500

    finally:
        if connection is not None:
            connection.close()


@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or request.form

    email = str(data.get("email", "")).strip().lower()
    temporary_password = str(data.get("temporary_password", ""))
    new_password = str(data.get("new_password", ""))
    confirm_password = str(data.get("confirm_password", ""))

    if (
        not email
        or not temporary_password
        or not new_password
        or not confirm_password
    ):
        return jsonify(
            error=(
                "Email, temporary password, new password "
                "and confirmation are required"
            )
        ), 400

    if len(new_password) < 8:
        return jsonify(
            error="New password must contain at least 8 characters"
        ), 400

    if new_password != confirm_password:
        return jsonify(
            error="New password and confirmation do not match"
        ), 400

    reset_key = get_reset_password_key(email)
    connection = None

    try:
        stored_password_hash = redis_client.get(reset_key)

        if stored_password_hash is None:
            return jsonify(
                error=(
                    "Temporary password is invalid or expired. "
                    "Request a new one."
                )
            ), 401

        if not check_password_hash(
            stored_password_hash,
            temporary_password,
        ):
            return jsonify(
                error="Invalid temporary password"
            ), 401

        connection = get_db()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE LOWER(email) = %s
                """,
                (email,),
            )

            user = cursor.fetchone()

            if user is None:
                return jsonify(
                    error="Invalid password reset request"
                ), 400

            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
                """,
                (
                    generate_password_hash(new_password),
                    user["id"],
                ),
            )

        connection.commit()

        redis_client.delete(reset_key)

        return jsonify(
            message=(
                "Password changed successfully. "
                "Log in using your new password."
            )
        ), 200

    except redis.RedisError:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Redis password-reset operation failed")

        return jsonify(
            error="Password reset service temporarily unavailable"
        ), 503

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Password update failed")

        return jsonify(
            error="Unable to reset your password. Please try again later."
        ), 500

    finally:
        if connection is not None:
            connection.close()


@app.route("/change-password", methods=["POST"])
def change_password():
    data = request.get_json(silent=True) or request.form

    username_or_email = str(
        data.get("username", data.get("email", ""))
    ).strip().lower()

    current_password = str(data.get("current_password", ""))
    new_password = str(data.get("new_password", ""))

    if not username_or_email or not current_password or not new_password:
        return jsonify(
            error=(
                "Username/email, current password and new password "
                "are required"
            )
        ), 400

    if len(new_password) < 8:
        return jsonify(
            error="New password must contain at least 8 characters"
        ), 400

    connection = get_db()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, password_hash
                FROM users
                WHERE LOWER(username) = %s OR LOWER(email) = %s
                """,
                (username_or_email, username_or_email),
            )

            user = cursor.fetchone()

        if user is None or not check_password_hash(
            user["password_hash"], current_password
        ):
            return jsonify(
                error="Invalid username/email or current password"
            ), 401

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
                """,
                (
                    generate_password_hash(new_password),
                    user["id"],
                ),
            )

        connection.commit()

    finally:
        connection.close()

    return jsonify(message="Password changed successfully"), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5006")),
        debug=False,
    )
