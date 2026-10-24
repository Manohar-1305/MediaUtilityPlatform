import os
import logging

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

from config import (
    PORT,
    PAYMENT_TITLE,
    PAYMENT_UPI_ID,
    PAYMENT_QR_CODE,
    MAX_CONTENT_LENGTH,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/")
def index():
    return render_template(
        "index.html",
        payment_title=PAYMENT_TITLE,
        payment_upi_id=PAYMENT_UPI_ID,
        qr_code=secure_filename(PAYMENT_QR_CODE),
    )


@app.get("/health")
def health():
    return jsonify(service="payment", status="healthy"), 200


@app.post("/submit")
def submit_payment_reference():
    name = request.form.get("name", "").strip()
    amount = request.form.get("amount", "").strip()
    reference = request.form.get("reference", "").strip()

    if not name:
        return jsonify(error="Enter your name."), 400

    try:
        amount_value = float(amount)
        if not 0 < amount_value <= 10000000:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="Enter a valid payment amount."), 400

    if not reference or len(reference) > 100:
        return jsonify(error="Enter a valid payment reference."), 400

    # Demo only: no payment provider is contacted and no payment is verified.
    logger.info(
        "Demo payment reference submitted: name=%s amount=%.2f reference=%s",
        name[:100],
        amount_value,
        reference[:100],
    )

    return render_template(
        "index.html",
        payment_title=PAYMENT_TITLE,
        payment_upi_id=PAYMENT_UPI_ID,
        qr_code=secure_filename(PAYMENT_QR_CODE),
        submitted=True,
        submitted_name=name,
        submitted_amount=f"{amount_value:.2f}",
        submitted_reference=reference,
    )


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error="Request exceeds the size limit."), 413


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True,
    )