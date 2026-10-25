
import io
import logging
import os

from flask import Flask, jsonify, request, send_file, render_template
from pypdf import PdfReader, PdfWriter
from werkzeug.utils import secure_filename

from redis_cache import cache_ping
from redis_cache_hooks import (
    build_merge_cache_key,
    get_cached_pdf,
    store_cached_pdf,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

MAX_FILES = 30
MAX_PAGES = 1000

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "pdf-combiner",
        "redis": "available" if cache_ping() else "unavailable",
    })


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({
        "error": "Total upload size cannot exceed 100 MB."
    }), 413


@app.post("/merge")
def merge_pdfs():
    files = request.files.getlist("files")

    if len(files) < 2:
        return jsonify({
            "error": "Upload at least two PDF files."
        }), 400

    if len(files) > MAX_FILES:
        return jsonify({
            "error": f"You can combine a maximum of {MAX_FILES} files."
        }), 400

    uploaded_data = []

    for uploaded in files:
        if not uploaded.filename:
            return jsonify({
                "error": "A selected file has no filename."
            }), 400

        filename = secure_filename(uploaded.filename)

        if not filename.lower().endswith(".pdf"):
            return jsonify({
                "error": f"{filename}: only PDF files are supported."
            }), 400

        data = uploaded.read()

        if not data:
            return jsonify({
                "error": f"{filename}: the file is empty."
            }), 400

        uploaded_data.append((filename, data))

    # Cache key includes ordered filenames and file contents.
    key = build_merge_cache_key(uploaded_data)

    # Redis failures are handled by the cache helpers.
    cached_pdf = get_cached_pdf(key)

    if cached_pdf is not None:
        app.logger.info("PDF merge cache hit")
        return send_file(
            io.BytesIO(cached_pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="combined.pdf",
            max_age=0,
        )

    app.logger.info("PDF merge cache miss")

    writer = PdfWriter()
    total_pages = 0

    try:
        for filename, data in uploaded_data:
            try:
                reader = PdfReader(io.BytesIO(data), strict=True)

                if reader.is_encrypted:
                    return jsonify({
                        "error": f"{filename}: encrypted PDFs are not supported."
                    }), 400

                page_count = len(reader.pages)

                if page_count == 0:
                    return jsonify({
                        "error": f"{filename}: the PDF has no pages."
                    }), 400

                total_pages += page_count

                if total_pages > MAX_PAGES:
                    return jsonify({
                        "error": (
                            f"Combined PDFs cannot exceed "
                            f"{MAX_PAGES} pages."
                        )
                    }), 400

                for page in reader.pages:
                    writer.add_page(page)

            except Exception:
                return jsonify({
                    "error": f"{filename}: invalid or unreadable PDF."
                }), 400

        output = io.BytesIO()
        writer.write(output)
        pdf_bytes = output.getvalue()

        # The cache helper skips results larger than the configured limit.
        store_cached_pdf(key, pdf_bytes)

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="combined.pdf",
            max_age=0,
        )

    except Exception:
        app.logger.exception("PDF combination failed")
        return jsonify({
            "error": "Unable to combine the selected PDFs."
        }), 500

    finally:
        writer.close()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5005")),
        debug=False,
        threaded=True,
    )
