from redis_cache import cache_key, cache_get, cache_set

import io
import os
import subprocess
import tempfile
import hashlib

import imageio_ffmpeg
from flask import Flask, jsonify, render_template, request, send_file
from redis_cache_hooks import init_redis_cache

app = Flask(__name__)
init_redis_cache(app, "video-to-gif")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg",
}
ALLOWED_FPS = {5, 8, 10, 12, 15}
ALLOWED_WIDTHS = {240, 320, 480, 640}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "healthy", "service": "video-to-gif"}), 200


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "The uploaded video exceeds 100 MB."}), 413


@app.post("/convert")
def convert():
    uploaded_file = request.files.get("file")

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "Please select a video file."}), 400

    original_name = os.path.basename(uploaded_file.filename)
    extension = os.path.splitext(original_name)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Unsupported video format."}), 400

    try:
        start = float(request.form.get("start", "0"))
        duration = float(request.form.get("duration", "5"))
        fps = int(request.form.get("fps", "10"))
        width = int(request.form.get("width", "480"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid conversion settings."}), 400

    if start < 0 or start > 36000:
        return jsonify({"error": "Start time must be between 0 and 36000 seconds."}), 400
    if duration < 0.1 or duration > 30:
        return jsonify({"error": "Duration must be between 0.1 and 30 seconds."}), 400
    if fps not in ALLOWED_FPS:
        return jsonify({"error": "Select a supported frame rate."}), 400
    if width not in ALLOWED_WIDTHS:
        return jsonify({"error": "Select a supported GIF width."}), 400

    video_data = uploaded_file.read()
    if not video_data:
        return jsonify({"error": "The uploaded video is empty."}), 400

    settings = {
        "start": start,
        "duration": duration,
        "fps": fps,
        "width": width,
        "format": "gif-v1",
    }
    key = cache_key("video-to-gif", video_data, settings)

    try:
        cached_gif = cache_get(key)
        if cached_gif is not None:
            app.logger.info("Redis cache HIT: filename=%s", original_name)
            response = send_file(
                io.BytesIO(cached_gif),
                mimetype="image/gif",
                as_attachment=True,
                download_name=os.path.splitext(original_name)[0] + ".gif",
                max_age=0,
            )
            response.headers["X-Redis-Cache"] = "HIT"
            response.headers["Cache-Control"] = "no-store"
            return response
        app.logger.info("Redis cache MISS: filename=%s", original_name)
    except Exception:
        app.logger.exception("Redis cache read failed")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    try:
        with tempfile.TemporaryDirectory(prefix="video_to_gif_") as temp_dir:
            input_path = os.path.join(temp_dir, f"input{extension}")
            output_path = os.path.join(temp_dir, "output.gif")
            palette_path = os.path.join(temp_dir, "palette.png")

            with open(input_path, "wb") as input_file:
                input_file.write(video_data)

            palette_command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-t", str(duration),
                "-i", input_path,
                "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,palettegen=stats_mode=diff",
                "-frames:v", "1", palette_path,
            ]
            palette_result = subprocess.run(
                palette_command, capture_output=True, text=True,
                timeout=180, check=False,
            )

            if palette_result.returncode != 0 or not os.path.isfile(palette_path):
                app.logger.error("FFmpeg palette generation failed: %s", palette_result.stderr)
                return jsonify({"error": "Could not process this video. Check that it is valid and try again."}), 422

            conversion_command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-t", str(duration),
                "-i", input_path, "-i", palette_path,
                "-filter_complex",
                f"fps={fps},scale={width}:-1:flags=lanczos[video];[video][1:v]paletteuse=dither=bayer:bayer_scale=5",
                "-loop", "0", output_path,
            ]
            conversion_result = subprocess.run(
                conversion_command, capture_output=True, text=True,
                timeout=180, check=False,
            )

            if conversion_result.returncode != 0 or not os.path.isfile(output_path):
                app.logger.error("FFmpeg GIF conversion failed: %s", conversion_result.stderr)
                return jsonify({"error": "GIF conversion failed. Try another video or lower the output width."}), 422

            with open(output_path, "rb") as gif_file:
                gif_data = gif_file.read()

        try:
            if cache_set(key, gif_data):
                app.logger.info(
                    "Redis cache STORE: filename=%s bytes=%s",
                    original_name, len(gif_data),
                )
            else:
                app.logger.warning(
                    "Redis cache STORE skipped or failed: filename=%s bytes=%s",
                    original_name, len(gif_data),
                )
        except Exception:
            app.logger.exception("Redis cache write failed")

        response = send_file(
            io.BytesIO(gif_data),
            mimetype="image/gif",
            as_attachment=True,
            download_name=os.path.splitext(original_name)[0] + ".gif",
            max_age=0,
        )
        response.headers["X-Redis-Cache"] = "MISS"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Conversion timed out. Try a shorter clip or smaller output width."}), 408
    except Exception:
        app.logger.exception("Unexpected error during video-to-GIF conversion")
        return jsonify({"error": "An unexpected error occurred during conversion."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5014, debug=False)
