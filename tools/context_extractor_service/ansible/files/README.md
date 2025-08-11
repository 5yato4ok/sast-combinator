## Install / Use

```bash
# example usage (local file)
python -m context_extractor.cli --file path/to/file.cpp --line 5 --compress
```

Public API:

```python
from context_extractor import extract_function_from_source, compress_function_from_source
from context_extractor import extract_function, compress_function, load_source_from_url
```

Key modules:
- `config.py`: language node sets & comment styles
- `ts_utils.py`: language loading, parser creation, node helpers
- `comments.py`: comment-only lines and inline comment masking
- `header.py`: multi-line function header capture
- `indent.py`: minimal dedent
- `identifiers.py`: identifier collection & read/write/loop logic
- `compress.py`: compacting algorithm
- `extract.py`: full-function extraction and URL wrappers
- `io.py`: URL/file loading
- `cli.py`: tiny CLI for quick tests
