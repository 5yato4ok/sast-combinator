# 🧠 Function Extractor API with Tree-sitter

This project provides a **web API service** that extracts the full body of the function that contains a specified line number from source code files. It supports direct file uploads or links (including GitHub URLs).

Parsing is powered by [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), a fast and robust parser generator used for syntax-aware code analysis.

---

## 📦 Requirements

* Python 3.9+
* Flask
* `tree_sitter` Python bindings
* Tree-sitter grammars:

  * `tree-sitter-cpp`
  * `tree-sitter-python`
  * `tree-sitter-javascript`

---

## 🛠 Installation

```bash
pip3 install flask tree_sitter tree-sitter-cpp tree-sitter-python tree-sitter-javascript
```

---

## 🚀 API Usage

### Endpoint

```
POST /function/extract
```

---

### 📂 1. Upload a Local File

**Request:**

```bash
curl -X POST http://localhost:8080/function/extract \
  -F "file=@./example.cpp" \
  -F "line_number=42"
```

**Response:**

```json
{
  "function": "void example() {\n  // ...\n}"
}
```

---

### 🌐 2. Use a File URL

Supports direct links or GitHub URLs like:

* `https://raw.githubusercontent.com/...`
* `https://github.com/user/repo/blob/branch/path/to/file.cpp`

**Request:**

```bash
curl -X POST http://localhost:8080/function/extract \
  -H "Content-Type: application/json" \
  -d '{
    "file_url": "https://github.com/networkoptix/nx_open/blob/master/vms/client/nx_vms_client_core/src/camera/camera_bookmark_aggregation.cpp",
    "line_number": 30
}'
```

**Response:**

```json
{
  "function": "void aggregateBookmarks(...) {\n    // ...\n}"
}
```

---

## 🌐 Supported Languages

| File Extension                            | Language   |
|-------------------------------------------| ---------- |
| `.py`                                     | Python     |
| `.cpp`, `.cc`, `.h`, `.hpp`, `.cxx`, `.c` | C++        |
| `.js`                                     | JavaScript |

To add support for more languages (e.g., TypeScript, Go, Rust), extend the `SUPPORTED_LANGUAGES` dictionary in `func_locator.py`.

---

## 📁 File Structure

* `app.py` – Flask server exposing the `/function/extract` endpoint.
* `func_locator.py` – Core logic using Tree-sitter for language parsing and function extraction.

---

## 🧪 Local Testing

```bash
FLASK_APP=app.py flask run --host=0.0.0.0 --port=8080
```

Then test using `curl`, Postman, or a frontend integration.
