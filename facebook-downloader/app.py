
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PORT = 5018
DOWNLOAD_DIR = Path("/tmp/facebook-downloader")
MAX_DOWNLOAD_SECONDS = 300
MAX_FILE_SIZE_MB = 500
MAX_CONCURRENT_DOWNLOADS = 2

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_DOWNLOADS)
jobs = {}
jobs_lock = threading.Lock()

ALLOWED_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.watch",
    "www.fb.watch",
}

from flask import render_template

@app.get("/")
def index():
    return render_template("index.html")

def valid_facebook_url(url):
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() in ALLOWED_HOSTS
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def download_video(job_id, url):
    if not semaphore.acquire(blocking=False):
        with jobs_lock:
            jobs[job_id] = {
                "status": "failed",
                "error": "Download capacity reached. Try again later.",
            }
        return

    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            raise RuntimeError("yt-dlp is not installed.")

        with jobs_lock:
            jobs[job_id] = {"status": "downloading"}

        command = [
            ytdlp,
            "--no-playlist",
            "--max-filesize", f"{MAX_FILE_SIZE_MB}M",
            "--socket-timeout", "20",
            "--retries", "2",
            "--format", "best[ext=mp4]/best",
            "--output", str(job_dir / "%(title).150B-%(id)s.%(ext)s"),
            "--print", "after_move:filepath",
            url,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=MAX_DOWNLOAD_SECONDS,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                (result.stderr or "Download failed")[-1500:]
            )

        file_path = None

        for line in reversed(result.stdout.splitlines()):
            candidate = Path(line.strip())
            if (
                candidate.is_file()
                and candidate.resolve().parent == job_dir.resolve()
            ):
                file_path = candidate
                break

        if not file_path:
            files = [p for p in job_dir.iterdir() if p.is_file()]
            if files:
                file_path = max(files, key=lambda p: p.stat().st_mtime)

        if not file_path or not file_path.is_file():
            raise RuntimeError("Downloaded video file was not found.")

        if file_path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise RuntimeError("Downloaded file exceeds the size limit.")

        with jobs_lock:
            jobs[job_id] = {
                "status": "completed",
                "filename": file_path.name,
                "size_bytes": file_path.stat().st_size,
            }

    except subprocess.TimeoutExpired:
        shutil.rmtree(job_dir, ignore_errors=True)
        with jobs_lock:
            jobs[job_id] = {
                "status": "failed",
                "error": "Download timed out.",
            }

    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        with jobs_lock:
            jobs[job_id] = {
                "status": "failed",
                "error": str(exc)[:1500],
            }

    finally:
        semaphore.release()


@app.get("/health")
def health():
    return jsonify({
        "service": "facebook-downloader",
        "status": "healthy",
    })


@app.post("/download")
def start_download():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not valid_facebook_url(url):
        return jsonify({
            "error": "Provide a valid HTTPS Facebook video or Reel URL."
        }), 400

    job_id = uuid.uuid4().hex

    with jobs_lock:
        jobs[job_id] = {"status": "queued"}

    threading.Thread(
        target=download_video,
        args=(job_id, url),
        daemon=True,
    ).start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/facebook-downloader/status/{job_id}",
        "download_url": f"/facebook-downloader/file/{job_id}",
    }), 202


@app.get("/status/<job_id>")
def download_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify({"job_id": job_id, **job})


@app.get("/file/<job_id>")
def download_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job.get("status") != "completed":
        return jsonify({
            "error": "Video is not ready.",
            "status": job.get("status"),
        }), 409

    job_dir = (DOWNLOAD_DIR / job_id).resolve()
    file_path = (job_dir / job["filename"]).resolve()

    if file_path.parent != job_dir or not file_path.is_file():
        return jsonify({"error": "Video file not found."}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_path.name,
        conditional=True,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
