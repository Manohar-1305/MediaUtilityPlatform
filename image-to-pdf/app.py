from redis_cache_hooks import init_redis_cache
from redis_cache import cache_key, cache_get, cache_set

import hashlib
import io
import os
import logging

from flask import Flask, render_template, request, send_file, jsonify, make_response
from PIL import Image, ImageFile, UnidentifiedImageError
from reportlab.lib.pagesizes import (
    A4, A3, A5, LETTER, LEGAL, landscape, portrait
)
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

app = Flask(__name__)
init_redis_cache(app, "image-to-pdf")

MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config["MAX_FORM_MEMORY_SIZE"] = 16 * 1024 * 1024
app.config["MAX_FORM_PARTS"] = 10000

Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"
}

PAGE_SIZES = {
    "A3": A3,
    "A4": A4,
    "A5": A5,
    "LETTER": LETTER,
    "LEGAL": LEGAL,
}

MARGINS = {"none": 0, "small": 18, "big": 36}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"status": "healthy"}, 200


@app.post("/convert")
def convert():
    images = []
    cache_key_value = None

    try:
        uploaded_files = request.files.getlist("images")

        if not uploaded_files or not any(f.filename for f in uploaded_files):
            logger.error(
                "No images received. Content-Type=%s Content-Length=%s "
                "Form=%s Files=%s",
                request.content_type,
                request.content_length,
                list(request.form.keys()),
                list(request.files.keys()),
            )
            return jsonify(
                error="No images received. Verify the upload form and gateway."
            ), 400

        orientation = request.form.get("orientation", "portrait").lower()
        page_size_name = request.form.get("page_size", "A4").upper()
        margin_name = request.form.get("margin", "none").lower()

        if orientation not in {"portrait", "landscape"}:
            return jsonify(error="Invalid page orientation."), 400

        if page_size_name not in PAGE_SIZES:
            return jsonify(error="Invalid page size."), 400

        if margin_name not in MARGINS:
            return jsonify(error="Invalid margin option."), 400

        image_data = []
        for uploaded_file in uploaded_files:
            if not uploaded_file.filename:
                continue

            filename = secure_filename(uploaded_file.filename)
            extension = os.path.splitext(filename)[1].lower()

            if extension not in ALLOWED_EXTENSIONS:
                return jsonify(
                    error=f"Unsupported image format: {filename}"
                ), 400

            try:
                file_bytes = uploaded_file.stream.read()
                uploaded_file.stream.seek(0)

                image_data.append({
                    "filename": filename,
                    "extension": extension,
                    "bytes": file_bytes,
                })

                with Image.open(io.BytesIO(file_bytes)) as source:
                    source.load()
                    images.append(source.convert("RGB"))

            except (UnidentifiedImageError, OSError, ValueError) as exc:
                logger.exception("Unable to process image %s", filename)
                return jsonify(
                    error=f"Unable to process image {filename}: {exc}"
                ), 400

        if not images:
            return jsonify(error="No valid images received."), 400

        cache_input = hashlib.sha256()
        for item in image_data:
            cache_input.update(item["filename"].encode("utf-8"))
            cache_input.update(b"\0")
            cache_input.update(item["bytes"])
            cache_input.update(b"\0")

        settings = {
            "service": "image-to-pdf",
            "orientation": orientation,
            "page_size": page_size_name,
            "margin": margin_name,
        }

        cache_key_value = cache_key(
            "image-to-pdf",
            cache_input.digest(),
            settings,
        )

        cached_pdf = cache_get(cache_key_value)
        if cached_pdf is not None:
            logger.info("Redis cache HIT for image-to-pdf")
            response = make_response(cached_pdf)
            response.headers["Content-Type"] = "application/pdf"
            response.headers[
                "Content-Disposition"
            ] = 'attachment; filename="converted-images.pdf"'
            response.headers["X-Redis-Cache"] = "HIT"
            return response

        base_size = PAGE_SIZES[page_size_name]
        page_dimensions = (
            landscape(base_size)
            if orientation == "landscape"
            else portrait(base_size)
        )

        page_width, page_height = page_dimensions
        margin = MARGINS[margin_name]
        available_width = page_width - 2 * margin
        available_height = page_height - 2 * margin

        if available_width <= 0 or available_height <= 0:
            return jsonify(
                error="Margins leave no usable page area."
            ), 400

        output = io.BytesIO()
        pdf = canvas.Canvas(output, pagesize=page_dimensions)

        for image in images:
            image_width, image_height = image.size

            scale = min(
                available_width / image_width,
                available_height / image_height,
            )

            rendered_width = image_width * scale
            rendered_height = image_height * scale
            x = (page_width - rendered_width) / 2
            y = (page_height - rendered_height) / 2

            pdf.drawImage(
                ImageReader(image),
                x,
                y,
                width=rendered_width,
                height=rendered_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            pdf.showPage()

        pdf.save()
        pdf_bytes = output.getvalue()

        if cache_key_value:
            if cache_set(cache_key_value, pdf_bytes):
                logger.info(
                    "Redis cache MISS: stored image-to-pdf output (%s bytes)",
                    len(pdf_bytes),
                )
            else:
                logger.info(
                    "Image-to-PDF output not cached (size limit or Redis unavailable)"
                )

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers[
            "Content-Disposition"
        ] = 'attachment; filename="converted-images.pdf"'
        response.headers["X-Redis-Cache"] = "MISS"
        response.headers["Cache-Control"] = "no-store"
        return response

    except Exception as exc:
        logger.exception("Image-to-PDF conversion failed")
        return jsonify(error=f"Conversion failed: {exc}"), 500

    finally:
        for image in images:
            try:
                image.close()
            except Exception:
                logger.exception("Failed to close image")


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error="Upload exceeds the 2 GB service limit."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5008, debug=False)
