
import io
import os
from flask import Flask, jsonify, request, send_file, render_template
from pypdf import PdfReader, PdfWriter
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

MAX_FILES = 30
MAX_PAGES = 1000


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "pdf-combiner"
    })


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "Total upload size cannot exceed 100 MB."}), 413


@app.post("/merge")
def merge_pdfs():
    files = request.files.getlist("files")

    if len(files) < 2:
        return jsonify({"error": "Upload at least two PDF files."}), 400

    if len(files) > MAX_FILES:
        return jsonify({
            "error": f"You can combine a maximum of {MAX_FILES} files."
        }), 400

    writer = PdfWriter()
    total_pages = 0

    try:
        for uploaded in files:
            if not uploaded.filename:
                return jsonify({"error": "A selected file has no filename."}), 400

            filename = secure_filename(uploaded.filename)

            if not filename.lower().endswith(".pdf"):
                return jsonify({
                    "error": f"{filename}: only PDF files are supported."
                }), 400

            data = uploaded.read()

            if not data:
                return jsonify({"error": f"{filename}: the file is empty."}), 400

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
                        "error": f"Combined PDFs cannot exceed {MAX_PAGES} pages."
                    }), 400

                for page in reader.pages:
                    writer.add_page(page)

            except Exception:
                return jsonify({
                    "error": f"{filename}: invalid or unreadable PDF."
                }), 400

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)

        return send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="combined.pdf",
            max_age=0
        )

    except Exception:
        app.logger.exception("PDF combination failed")
        return jsonify({"error": "Unable to combine the selected PDFs."}), 500

    finally:
        writer.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5005")))
