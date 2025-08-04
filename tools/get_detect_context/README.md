# Function Extractor with Tree-sitter

This Python module allows you to extract the full body of a function that contains a specific line in a source file. It uses [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse the source code and works with multiple programming languages.

---

## 📦 Requirements

- Python 3.9+
- `tree_sitter` Python bindings

---

## 🛠 Installation

```bash
# Install the tree-sitter Python wrapper
pip3 install tree_sitter tree-sitter-cpp tree-sitter-python tree-sitter-javascript

```

---

## 🚀 Usage

```python
from func_locator import extract_function

function_body = extract_function("example.cpp",  42)
if function_body:
    print(function_body)
else:
    print("No function found at the given line.")
```

---

## 🌐 Supported Languages

| File Extension            | Language    | Grammar Repo                      |
|---------------------------|-------------|-----------------------------------|
| `.py`                     | Python      | tree-sitter-python                |
| `.cpp`, `.cc`, `h`, `hpp` | C++         | tree-sitter-cpp                   |
| `.js`                     | JavaScript  | tree-sitter-javascript            |

You can easily add more languages by extending the `SUPPORTED_LANGUAGES` dictionary in `func_locator.py`.