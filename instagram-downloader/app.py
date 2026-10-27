
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_file
from yt_dlp import YoutubeDL

app = Flask(__name__)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "instagram-downloader"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}

URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def validate_instagram_url(value):
    if not value or not URL_PATTERN.match(value.strip()):
        return False

    parsed = urlparse(value.strip())
    return (
        parsed.scheme in ("http", "https")
        and parsed.hostname in INSTAGRAM_HOSTS
        and parsed.port in (None, 80, 443)
        and parsed.username is None
        and parsed.password is None
    )


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"service": "instagram-downloader", "status": "ok"})


@app.post("/download")
def download():
    data = request.get_json(silent=True) or {}
    video_url = str(data.get("url", "")).strip()

    if not validate_instagram_url(video_url):
        return jsonify({
            "error": "Enter a valid Instagram Reel or video URL."
        }), 400

    job_dir = Path(tempfile.mkdtemp(prefix="ig-", dir=DOWNLOAD_DIR))

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(job_dir / "instagram_video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": 500 * 1024 * 1024,
        "socket_timeout": 30,
    }

    try:
        with YoutubeDL(options) as ydl:
            ydl.download([video_url])

        files = [
            path for path in job_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {
                ".mp4", ".webm", ".mkv", ".mov"
            }
        ]

        if not files:
            return jsonify({
                "error": "Instagram did not provide a downloadable video."
            }), 422

        video_file = max(files, key=lambda path: path.stat().st_size)

        return send_file(
            video_file,
            as_attachment=True,
            download_name="instagram_video" + video_file.suffix,
            mimetype="application/octet-stream",
            conditional=True,
        )

    except Exception:
        app.logger.exception("Instagram download failed")
        return jsonify({
            "error": (
                "Unable to download this video. It may be private, "
                "restricted, unavailable, or unsupported by the current "
                "yt-dlp version."
            )
        }), 422


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5019)
