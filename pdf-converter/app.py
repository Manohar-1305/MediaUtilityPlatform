import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from redis_cache import cache_get, cache_key, cache_set, redis_client

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


@app.get("/health")
def health():
    try:
        redis_ok = bool(redis_client.ping())
    except Exception:
        redis_ok = False

    return jsonify(
        status="healthy",
        service="pdf-converter",
        libreoffice=shutil.which("libreoffice") is not None,
        redis=redis_ok,
    )


@app.post("/convert-file")
def convert_file():
    uploaded = request.files.get("file") or request.files.get("document")

    if not uploaded or not uploaded.filename:
        return jsonify(error="Upload a Word document using the file field."), 400

    filename = Path(uploaded.filename).name
    extension = Path(filename).suffix.lower()

    if extension not in {".doc", ".docx"}:
        return jsonify(error="Only DOC and DOCX files are supported."), 400

    libreoffice = shutil.which("libreoffice")
    if not libreoffice:
        return jsonify(error="Document conversion is unavailable."), 500

    document_data = uploaded.read()

    if not document_data:
        return jsonify(error="The uploaded document is empty."), 400

    settings = {
        "extension": extension,
        "format": "pdf",
        "converter_version": "libreoffice-pdf-v1",
    }

    digest = hashlib.sha256(document_data).digest()
    key = cache_key("pdf-converter", digest, settings)

    try:
        cached_pdf = cache_get(key)

        if cached_pdf is not None and cached_pdf.startswith(b"%PDF-"):
            app.logger.info("Redis cache HIT: %s", key)
            return send_file(
                io.BytesIO(cached_pdf),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=Path(filename).stem + ".pdf",
                max_age=0,
                etag=False,
            ), 200, {"X-Redis-Cache": "HIT"}

        app.logger.info("Redis cache MISS: %s", key)

        with tempfile.TemporaryDirectory(prefix="pdf_converter_") as temp_dir:
            workdir = Path(temp_dir)
            input_path = workdir / filename
            output_dir = workdir / "output"
            profile_dir = workdir / "lo-profile"

            output_dir.mkdir()
            profile_dir.mkdir()
            input_path.write_bytes(document_data)

            command = [
                libreoffice,
                "-env:UserInstallation=" + profile_dir.as_uri(),
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(input_path),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )

            output_path = output_dir / (input_path.stem + ".pdf")

            if result.returncode != 0 or not output_path.is_file():
                app.logger.error(
                    "LibreOffice conversion failed: %s",
                    result.stderr[-4000:],
                )
                return jsonify(
                    error="Conversion failed. The document may be damaged or unsupported."
                ), 422

            pdf_data = output_path.read_bytes()

            if not pdf_data.startswith(b"%PDF-"):
                return jsonify(error="The converted PDF is invalid."), 500

        if cache_set(key, pdf_data):
            app.logger.info(
                "Redis cache STORE: %s (%d bytes)", key, len(pdf_data)
            )
        else:
            app.logger.warning(
                "Redis cache STORE skipped or failed: %s (%d bytes)",
                key, len(pdf_data)
            )

        return send_file(
            io.BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=Path(filename).stem + ".pdf",
            max_age=0,
            etag=False,
        ), 200, {"X-Redis-Cache": "MISS"}

    except subprocess.TimeoutExpired:
        return jsonify(error="Conversion timed out. Try a smaller document."), 504

    except Exception:
        app.logger.exception("PDF conversion failed")
        return jsonify(error="An unexpected conversion error occurred."), 500


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error="Maximum upload size is 50 MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5004")), debug=False)
