
import os

PORT = int(os.getenv("PORT", "5016"))
PAYMENT_TITLE = os.getenv("PAYMENT_TITLE", "Support Our Work")
PAYMENT_UPI_ID = os.getenv("PAYMENT_UPI_ID", "manohar.shetty10-1@okicici")
PAYMENT_QR_CODE = os.getenv("PAYMENT_QR_CODE", "qr-code.png")
MAX_CONTENT_LENGTH = 16 * 1024 * 1024
