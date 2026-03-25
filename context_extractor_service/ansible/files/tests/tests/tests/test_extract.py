
import os, sys
from pathlib import Path

# Ensure our test package is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source

CASES = [
    ("example.py", "def foo():\n  c = 1+3\n  return 1\n", 1),
    ("test.h", "int foo(){ int c = 1+3;\n return 1; }\n", 1),
    ("test.hpp", "int foo(){ int c = 1+3;\n return 1; }\n", 1),
    ("test.cpp", "int foo(){ int c = 1+3;\nreturn 1; }\n", 1),
    ("test.c", "int foo(){ return 1; }\n", 1),
    ("test.cc", "int foo(){ return 1; }\n", 1),
    ("test.cxx", "int foo(){ return 1; }\n", 1),
    ("app.js", "function foo(){ return 1; }\n", 1),
    ("mod.mjs", "export function foo(){ return 1; }\n", 1),
    ("mod.cjs", "function foo(){ return 1; }\n", 1),
    ("Main.java", "class A { int foo(){ return 1; } }\n", 1),
    ("Program.cs", "class A { int Foo(){ return 1; } }\n", 1),
    ("types.ts", "function foo(): number { return 1; }\n", 1),
    ("main.go", "package main\nfunc foo() int { return 1 }\n", 2),
    ("script.rb", "def foo\n  1\nend\n", 1),
    ("main.kt", "fun foo(): Int { return 1 }\n", 1),
    ("app.php", "<?php function foo() { return 1; }\n", 1),
]

def test_extract_across_languages():
    for fname, code, line in CASES:
        res = extract_function_from_source(code, fname, line, 200)
        assert isinstance(res, dict) and 'text' in res, f"No result for {fname}"
        text = res['text']
        # Basic sanity: the function name should be present
        assert 'foo' in text or 'Foo' in text, f"Function name not found in result for {fname}"
        # Should include a return-ish (ruby may have just '1')
        assert ('return' in text) or (fname.endswith('.rb')), f"Likely wrong region for {fname}: {text!r}"
