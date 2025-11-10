from __future__ import annotations
import argparse, sys
from pathlib import Path
from .extract import extract_function_from_source
from .compress import compress_function_from_source

def main():
    p = argparse.ArgumentParser(description="Code slicer")
    p.add_argument("--file", required=True, help="Path to local file")
    p.add_argument("--line", required=True, type=int, help="1-based line number")
    p.add_argument("--compress", action="store_true", help="Compress around line")
    args = p.parse_args()

    src = Path(args.file).read_text(encoding="utf-8", errors="replace")
    if args.compress:
        out = compress_function_from_source(src, Path(args.file).name, args.line)
    else:
        out = extract_function_from_source(src, Path(args.file).name, args.line)

    print(out["text"])
    print("\nMETA:", out["meta"], file=sys.stderr)

if __name__ == "__main__":
    main()
