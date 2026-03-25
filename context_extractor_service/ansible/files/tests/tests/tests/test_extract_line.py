
import os, sys
from pathlib import Path

# Ensure our test package is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


def test_code_on_line_inside_function():
    """
    When target_line is inside a function, the extractor should:
      - return full function text in "text"
      - include "code_on_line" with the smallest AST node covering target_line
      - keep meta fields including function_lines and relative_line_number
    """
    source = """\
def add(x, y):
    z = x + y
    return z

a = 42
"""
    # Lines are 1-based:
    # 1: def add(x, y):
    # 2:     z = x + y
    # 3:     return z      <-- target_line
    # 5: a = 42
    res = extract_function_from_source(source, "mod.py", line_number=3, max_lines=200)

    # "text" should be the entire function body
    assert "def add(x, y):" in res["text"]
    assert "return z" in res["text"]

    # Basic meta checks
    meta = res.get("meta", {})
    # "code_on_line" should contain the return statement node (or a parent node that still includes it)
    assert "return z" in (meta.get("code_on_line") or "")
    assert meta.get("target_line") == 3
    # function_lines should cover lines 1..3 for this tiny function
    assert meta.get("function_lines") == (1, 3)
    # relative_line_number for line 3, when function starts at line 1, is 3
    assert meta.get("relative_line_number") == 3


def test_code_on_line_when_function_not_found():
    """
    When target_line is NOT inside any function, the extractor should:
      - return "// Function not found." in "text"
      - still include "code_on_line" determined from the smallest AST node (or raw line fallback)
    """
    source = """\
import os

VALUE = 123

def f():
    return 1
"""
    # Lines (1-based):
    # 1: import os
    # 3: VALUE = 123      <-- target_line (outside any function)
    # 5-6: def f()...
    res = extract_function_from_source(source, "mod.py", line_number=3, max_lines=200)

    # Function is not found for line 3
    assert isinstance(res.get("text"), str)
    assert res["text"].startswith("// Function not found.")



    # Meta still should include the target line
    meta = res.get("meta", {})
    assert meta.get("target_line") == 3

    # But "code_on_line" must still be provided (either the AST node text or raw line content)
    col = meta.get("code_on_line")
    assert col is not None
    assert "VALUE = 123" in col

def _get_code_on_line_from_meta(res: dict) -> str:
    """
    Helper to fetch code_on_line from meta.
    Raises an assertion error if not present.
    """
    meta = res.get("meta", {})
    assert "code_on_line" in meta, "Expected 'code_on_line' to be stored in meta"
    return meta["code_on_line"]

def test_multiline_node_inside_function():
    """
    Target line is inside a multi-line AST node (e.g., a parenthesized/binary expression)
    within a function. The extractor should return the FULL multi-line node text
    (spanning >1 lines) in meta['code_on_line'].
    """
    source = """\
def f(x):
    if (
        x > 10
        and x % 2 == 0
    ):
        return 1
    return 0
"""
    # Lines (1-based):
    # 1: def f(x):
    # 2:     if (
    # 3:         x > 10           <-- target_line (inside a multi-line expression node)
    # 4:         and x % 2 == 0
    # 5:     ):
    # 6:         return 1
    # 7:     return 0
    res = extract_function_from_source(source, "mod.py", line_number=3, max_lines=200)

    # Function text is returned as usual
    assert "def f(x):" in res["text"]
    meta = res.get("meta", {})
    assert meta.get("function_lines") == (1, 7)
    assert meta.get("target_line") == 3

    # For a multi-line node, code_on_line must contain the full node text and span multiple lines.
    code_on_line = _get_code_on_line_from_meta(res)
    assert isinstance(code_on_line, str) and code_on_line.strip(), "code_on_line must be a non-empty string"

    # It should be multi-line (the node covers more than one line).
    assert len(code_on_line.splitlines()) > 1, "Expected multi-line node text in code_on_line"

    # Sanity checks: it should include fragments from different lines within the same node.
    assert "x > 10" in code_on_line
    assert "% 2 == 0" in code_on_line


def test_multiline_node_when_function_not_found():
    """
    Target line is not inside any function but inside a multi-line node at module level,
    e.g., a list/dict/set literal spanning multiple lines. The extractor should still put
    the FULL multi-line node text into meta['code_on_line'] and return the 'Function not found'
    message in 'text'.
    """
    source = """\
CONFIG = [
    1,
    2,
    3,
]

x = 42
"""
    # Lines (1-based):
    # 1: CONFIG = [
    # 2:     1,
    # 3:     2,         <-- target_line (inside a multi-line list literal)
    # 4:     3,
    # 5: ]
    # 7: x = 42
    res = extract_function_from_source(source, "mod.py", line_number=3, max_lines=200)

    # No function should be found for line 3
    assert isinstance(res.get("text"), str) and res["text"].startswith("// Function not found.")

    # code_on_line should still exist in meta and be multi-line
    code_on_line = _get_code_on_line_from_meta(res)
    assert len(code_on_line.splitlines()) > 1, "Expected multi-line node text in code_on_line (module-level)"
    # Sanity: should include several items of the literal
    assert "[" in code_on_line and "]" in code_on_line
    assert "1," in code_on_line and "2," in code_on_line and "3," in code_on_line
    
def test_python_multiline_dict_literal_inside_function():
    """
    Target line is inside a multi-line dict literal within a function.
    The extractor should return the full multi-line node text in meta['code_on_line'].
    """
    source = """\
def build():
    cfg = {
        "a": 1,
        "b": 2,
        "c": 3,
    }
    return cfg
"""
    # Lines: 1 def, 2 cfg = {, 3 "a": 1, 4 "b": 2 <-- target, 5 "c": 3, 6 }, 7 return
    res = extract_function_from_source(source, "mod.py", line_number=4, max_lines=200)
    code_on_line = _get_code_on_line_from_meta(res)

    # Should span multiple lines (the dict literal)
    assert len(code_on_line.splitlines()) > 1
    assert '"a": 1' in code_on_line and '"b": 2' in code_on_line and '"c": 3' in code_on_line
    assert code_on_line.strip().startswith("{") and code_on_line.strip().endswith("}")


# -------------------------
# C++: multiline 'if' condition inside a function
# -------------------------
def test_cpp_multiline_if_condition_inside_function():
    """
    Target line is inside a multi-line parenthesized condition in an if-statement.
    Expect the multi-line node text in meta['code_on_line'].
    """
    source = """\
int sum(int x, int y) {
    if (
        x > 10 &&
        y < 20
    ) {
        return x + y;
    }
}
"""
    # Lines: 1 sig, 2 if (, 3 x > 10 && <-- target, 4 y < 20, 5 ), 6 return ...
    res = extract_function_from_source(source, "foo.cpp", line_number=3, max_lines=200)
    code_on_line = _get_code_on_line_from_meta(res)

    # Should be the multi-line condition block "( ... )"
    assert len(code_on_line.splitlines()) > 1
    assert "x > 10" in code_on_line and "y < 20" in code_on_line


# -------------------------
# Ruby: multiline array literal inside a method
# -------------------------
def test_ruby_multiline_array_literal_inside_method():
    """
    Target line is inside a multi-line array literal in a Ruby method.
    Expect the full array literal (multi-line) in meta['code_on_line'].
    """
    source = """\
def make_list
  arr = [
    10,
    20,
    30,
  ]
  arr
end
"""
    # Lines: 1 def, 2 arr = [, 3 10,, 4 20, <-- target, 5 30,, 6 ], 7 arr, 8 end
    res = extract_function_from_source(source, "app.rb", line_number=4, max_lines=200)
    code_on_line = _get_code_on_line_from_meta(res)

    assert len(code_on_line.splitlines()) > 1
    assert "[" in code_on_line and "]" in code_on_line
    assert "10" in code_on_line and "20" in code_on_line and "30" in code_on_line


# -------------------------
# C#: multiline collection initializer inside a method
# -------------------------
def test_csharp_multiline_collection_initializer_inside_method():
    """
    Target line is inside a multi-line collection initializer in C#.
    Expect the full initializer text in meta['code_on_line'].
    """
    source = """\
using System.Collections.Generic;

class C {
    static List<int> Build() {
        var data = new List<int> {
            1,
            2,
            3,
        };
        return data;
    }
}
"""
    # Lines: 1-2 using/blank, 3 class, 4 method sig,
    # 5 var data = new List<int> {, 6 1,, 7 2, <-- target, 8 3,, 9 }, 10 return...
    res = extract_function_from_source(source, "prog.cs", line_number=7, max_lines=200)
    code_on_line = _get_code_on_line_from_meta(res)

    assert len(code_on_line.splitlines()) > 1
    # The multi-line initializer should be captured
    assert "1" in code_on_line and "2" in code_on_line and "3" in code_on_line
    assert "{" in code_on_line and "}" in code_on_line


# -------------------------
# JavaScript: multiline object literal at module scope (no function)
# -------------------------
def test_js_multiline_object_literal_outside_function():
    """
    Target line is inside a multi-line object literal at module level (no function).
    We pick a property of the OUTER object so that the multi-line ancestor is the outer object itself.
    """
    source = """\
const CONFIG = {
  host: "localhost",
  port: 8080,
  flags: {
    debug: true,
    trace: false,
  },
};

function f() { return 1; }
"""
    # Lines (1-based):
    # 1 const CONFIG = {
    # 2   host: "localhost",
    # 3   port: 8080,     <-- target_line (outer object property)
    # 4   flags: {
    # 5     debug: true,
    # 6     trace: false,
    # 7   },
    # 8 };
    res = extract_function_from_source(source, "app.js", line_number=3, max_lines=200)

    assert isinstance(res.get("text"), str) and res["text"].startswith("// Function not found.")
    code_on_line = _get_code_on_line_from_meta(res)

    assert len(code_on_line.splitlines()) > 1
    # Now we expect the OUTER object literal
    assert "host" in code_on_line and "port" in code_on_line
    assert "flags" in code_on_line and "debug" in code_on_line and "trace" in code_on_line
    assert "{" in code_on_line and "}" in code_on_line
