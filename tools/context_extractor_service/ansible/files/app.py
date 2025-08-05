import os
from flask import Flask, request, jsonify, abort
from urllib.parse import urlparse
from func_locator import extract_function, extract_function_from_source

app = Flask(__name__)

API_TOKEN = os.environ.get("API_TOKEN", "secret-token")  # по умолчанию

def require_auth(f):
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token or token != f"Bearer {API_TOKEN}":
            abort(401, description="Unauthorized")
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def convert_github_to_raw(url: str) -> str:
    """
    Convert GitHub blob URL to raw.githubusercontent.com format.
    """
    if "github.com" not in url:
        return url

    parsed = urlparse(url)
    if parsed.netloc != "github.com" or "/blob/" not in parsed.path:
        return url

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 5:
        raise ValueError("Invalid GitHub URL format")

    user, repo, _, branch, *file_path = parts
    return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{'/'.join(file_path)}"

@app.route("/function/extract", methods=["POST"])
@require_auth
def extract():
    try:
        line_number = int(request.form.get("line_number", 0) or request.json.get("line_number", 0))
        if not line_number:
            return jsonify({"error": "Missing line_number"}), 400

        # Case 1: File was uploaded via multipart/form-data
        if "file" in request.files:
            uploaded_file = request.files["file"]
            filename = uploaded_file.filename
            source_code = uploaded_file.read().decode("utf-8")
            result = extract_function_from_source(source_code, filename, line_number)
            return jsonify({"function": result or ""})

        # Case 2: file_url passed as JSON
        elif request.is_json:
            data = request.get_json()
            file_url = data.get("file_url")
            if not file_url:
                return jsonify({"error": "Missing file_url"}), 400

            file_url = convert_github_to_raw(file_url)
            result = extract_function(file_url, line_number)
            return jsonify({"function": result or ""})

        return jsonify({"error": "No valid input file or URL provided"}), 400

    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
