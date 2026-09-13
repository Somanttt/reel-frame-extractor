```python
import os
import json
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from datetime import datetime

app = Flask(__name__)

# Create a persistent frames directory in /tmp
FRAMES_DIR = Path(tempfile.gettempdir()) / "reel_frames"
FRAMES_DIR.mkdir(exist_ok=True)


@app.route('/extract', methods=['POST'])
def extract_frames():
    """
    Receives Zernio webhook JSON, extracts reel URL, downloads reel,
    extracts frames, and returns URLs to access those frames.
    """
    try:
        # Parse incoming JSON
        data = request.get_json()

        # Extract reel URL from Zernio webhook structure
        # Path: body.message.attachments[0].url
        reel_url = None

        if isinstance(data, list):
            data = data[0]  # If it's a list, take first item

        body = data.get('body', {})
        message = body.get('message', {})
        attachments = message.get('attachments', [])

        if attachments and len(attachments) > 0:
            reel_url = attachments[0].get('url')

        if not reel_url:
            return jsonify({"error": "No reel URL found in request"}), 400

        print(f"[{datetime.now()}] Extracting frames from: {reel_url}")

        # Create unique session directory for this reel
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        session_frames_dir = FRAMES_DIR / session_id
        session_frames_dir.mkdir(exist_ok=True)

        # Step 1: Download reel using yt-dlp
        reel_path = session_frames_dir / "reel.mp4"

        download_cmd = [
            'yt-dlp',
            '-o', str(reel_path),
            reel_url
        ]

        result = subprocess.run(
            download_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"yt-dlp error: {result.stderr}")
            return jsonify({
                "error": f"Failed to download reel: {result.stderr}"
            }), 400

        if not reel_path.exists():
            return jsonify({
                "error": "Reel downloaded but file not found"
            }), 400

        print(f"Reel downloaded: {reel_path}")

        # Step 2: Extract frames using ffmpeg
        # Extract frames every 0.4 seconds
        frame_pattern = session_frames_dir / "frame_%03d.jpg"

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(reel_path),
            '-vf', 'fps=1/0.4',
            '-q:v', '2',
            str(frame_pattern),
            '-y'
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr}")
            return jsonify({
                "error": f"Failed to extract frames: {result.stderr}"
            }), 400

        # Step 3: Collect extracted frames
        frames = sorted(session_frames_dir.glob("frame_*.jpg"))

        if not frames:
            return jsonify({
                "error": "No frames extracted from reel"
            }), 400

        print(f"Extracted {len(frames)} frames")

        # Step 4: Build response with frame URLs
        frame_data = []
        base_url = request.host_url.rstrip('/')

        for idx, frame_file in enumerate(frames, 1):
            frame_url = (
                f"{base_url}/frames/"
                f"{session_id}/frame_{idx:03d}.jpg"
            )

            frame_data.append({
                "index": idx,
                "url": frame_url,
                "filename": frame_file.name
            })

        # Cleanup: Delete the reel file (keep frames for now)
        try:
            reel_path.unlink()
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "frame_count": len(frames),
            "frames": frame_data
        }), 200

    except Exception as e:
        print(f"Error in /extract: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/frames/<session_id>/<filename>', methods=['GET'])
def serve_frame(session_id, filename):
    """
    Serves individual frames as binary image files.
    AI agent calls this to download specific frames.
    """
    try:
        # Security: Only allow frame files
        if not filename.startswith('frame_') or not filename.endswith('.jpg'):
            return jsonify({"error": "Invalid filename"}), 400

        frame_path = FRAMES_DIR / session_id / filename

        if not frame_path.exists():
            return jsonify({"error": "Frame not found"}), 404

        print(f"Serving frame: {frame_path}")

        return send_file(
            frame_path,
            mimetype='image/jpeg',
            as_attachment=False
        )

    except Exception as e:
        print(f"Error in /frames: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
```
