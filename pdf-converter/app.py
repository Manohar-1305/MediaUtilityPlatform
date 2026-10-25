cat > app.py <<'EOF'
import io
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

@app.get("/health")
def health():
    return jsonify(
        status="healthy",
        service="pdf-converter",
        libreoffice=shutil.which("libreoffice") is not None,
    )

@app.post("/convert-file")
def convert_file():
    uploaded = request.files.get("file") or request.files.get("document")

    if not uploaded or not uploaded.filename:
        return jsonify(error="Upload a Word document using the file field."), 400

    filename = Path(uploaded.filename).name

    if Path(filename).suffix.lower() not in {".doc", ".docx"}:
        return jsonify(error="Only DOC and DOCX files are supported."), 400

    libreoffice = shutil.which("libreoffice")
    if not libreoffice:
        app.logger.error("LibreOffice is not installed.")
        return jsonify(error="Document conversion is unavailable."), 500

    document_data = uploaded.read()

    if not document_data:
        return jsonify(error="The uploaded document is empty."), 400

    try:
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
                app.logger.error("LibreOffice produced an invalid PDF.")
                return jsonify(error="The converted PDF is invalid."), 500

        return send_file(
            io.BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=input_path.stem + ".pdf",
            max_age=0,
        )

    except subprocess.TimeoutExpired:
        return jsonify(error="Conversion timed out. Try a smaller document."), 504

    except Exception:
        app.logger.exception("PDF conversion failed")
        return jsonify(error="An unexpected conversion error occurred."), 500

@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error="Maximum upload size is 50 MB."), 413

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=False)

# ssh -i hetzner.key root@2.31.25.111