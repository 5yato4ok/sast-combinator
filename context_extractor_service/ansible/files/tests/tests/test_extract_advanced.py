
import sys
from pathlib import Path

# Make our local 'pkg' importable (as in previous setup)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source

def _assert_contains(text: str, needle: str):
    assert needle in text, f"Expected to find {needle!r} in extracted text.\n--- Extracted ---\n{text}\n------------------"

def _run_case(fname: str, code: str, probe_lines: list[int]):
    for ln in probe_lines:
        res = extract_function_from_source(code, fname, ln, max_lines=200)
        assert isinstance(res, dict) and 'text' in res and 'meta' in res
        txt = res['text']
        meta = res['meta']
        assert meta['target_line'] == ln
        # extraction shouldn't be empty
        assert len(txt.strip()) > 0
        # extracted text should be contiguous fragment from original
        assert txt.replace("\r\n", "\n") in code.replace("\r\n", "\n"), "Extractor returned a fragment not present verbatim in original code"


def test_python_decorators_and_nested():
    code = """\
def helper():
    return 0

@decorator1
@decorator2(param=42)
def foo(x, y):
    def inner(a):
        return a + 1
    if x > y:
        return inner(x)  # Ln 9
    else:
        return inner(y)

class C:
    @classmethod
    def bar(cls):
        return 'ok'
"""
    # probe inside foo: signature, body, inner call, and else branch
    _run_case("mod.py", code, [6, 7, 9, 11])
    # sanity: fragment should contain 'def foo' and 'return'
    res = extract_function_from_source(code, "mod.py", 7, max_lines=200)
    _assert_contains(res['text'], "def foo")
    _assert_contains(res['text'], "return")


def test_cpp_overloads_and_namespaces():
    code = """\
int add(int a, int b) { return a + b; }

namespace N {
int add(int a, int b, int c) {
    int s = a + b;
    return s + c; // ln6
}
}
"""
    _run_case("a.cpp", code, [1, 5, 6])
    res = extract_function_from_source(code, "a.cpp", 6, 200)
    _assert_contains(res['text'], "int add")
    _assert_contains(res['text'], "return")


def test_js_class_method_and_arrow():
    code = """\
// top-level function
function foo(a) {
  const x = n => n+1;
  return x(a); // ln4
}

class K {
  method(p) {
    return foo(p);
  }
}

// arrow at top level
const z = (m) => { return m * 2; };
"""
    _run_case("app.js", code, [3,4,9,14])
    res = extract_function_from_source(code, "app.js", 8, 200)
    _assert_contains(res['text'], "method(")


def test_typescript_generics_and_class_field_method():
    code = """\
class Box<T> {
  value: T;
  constructor(v: T) { this.value = v; }
  get(): T { return this.value; } // ln4
}

function foo<T extends number>(x: T): T {
  return x + 1;
}
"""
    _run_case("app.ts", code, [3,4,7])
    res = extract_function_from_source(code, "app.ts", 7, 200)
    _assert_contains(res['text'], "function foo")


def test_java_methods_and_overloads():
    code = """\
class A {
    int foo(int x) { if (x>0) return x; return -x; }
    String foo(String s) { return s.trim(); } // ln3
    static int bar() { return 1; }
}
"""
    _run_case("A.java", code, [2,3,4])
    res = extract_function_from_source(code, "A.java", 3, 200)
    _assert_contains(res['text'], "foo(")


def test_csharp_class_and_local_function():
    code = """\
class A {
    int Foo(int x) {
        int Inner(int t) { return t+1; } // ln3
        if (x>0) return Inner(x);
        return Inner(-x);
    }

    static string Bar() { return "ok"; }
}
"""
    _run_case("A.cs", code, [3,4,6,8])
    res = extract_function_from_source(code, "A.cs", 4, 200)
    _assert_contains(res['text'], "Foo(")


def test_go_receiver_and_plain_func():
    code = """\
package main

type S struct { v int }

func (s *S) Inc() int {
    s.v++
    return s.v // ln7
}

func Add(a, b int) int { return a + b }
"""
    _run_case("main.go", code, [6,7,10])
    res = extract_function_from_source(code, "main.go", 7, 200)
    _assert_contains(res['text'], "Inc(")


def test_ruby_methods_singleton_and_normal():
    code = """\
class C
  def self.k
    1
  end

  def foo(x)
    if x > 0
      x # ln9
    else
      -x
    end
  end
end
"""
    _run_case("a.rb", code, [3,7,9,12])
    res = extract_function_from_source(code, "a.rb", 9, 200)
    _assert_contains(res['text'], "def foo")


def test_kotlin_top_level_and_class_method():
    code = """\
fun inc(x: Int): Int {
    if (x > 0) return x + 1
    return 0 // ln3
}

class A {
    fun foo(s: String): String {
        return s.trim()
    }
}
"""
    _run_case("A.kt", code, [2,3,7,8])
    res = extract_function_from_source(code, "A.kt", 7, 200)
    _assert_contains(res['text'], "fun foo")
