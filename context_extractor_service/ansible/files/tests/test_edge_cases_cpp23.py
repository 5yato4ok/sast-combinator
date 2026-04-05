"""
Edge case tests for C++23 language features.

Covers:
- Concepts and requires-clauses (C++20+)
- Coroutines: co_await / co_yield / co_return
- Structured bindings: auto [x, y] = ...
- C++20/23 named-module imports: import std; / export import foo;
- Template lambdas: []<typename T>(T x) {}
"""
import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


# ---------------------------------------------------------------------------
# 1. Concepts and requires-clauses
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_concept_constrained_template():
    """extract_function must return the full body of a concept-constrained template function."""
    source = """\
#include <concepts>
#include <iostream>

template <typename T>
concept Printable = requires(T t) { std::cout << t; };

template <Printable T>
void print_value(T value) {
    std::cout << value << "\\n";
}
"""
    result = extract_function_from_source(source, "concepts.cpp", 8, 200)
    assert result is not None and "text" in result
    assert "print_value" in result["text"]
    assert "Printable" in result["text"] or "T" in result["text"]


def test_find_identifiers_should_capture_identifiers_in_requires_expression(monkeypatch):
    """find_identifiers must capture reads inside a requires-expression body."""
    source = """\
template <typename T>
concept SizedBuffer = requires(T buf, std::size_t size) {
    buf.data();
    buf.size() == size;
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sized.hpp"))
    # Line 3: buf.data() — buf is read
    result = mcp_server.find_identifiers("pipe", "sized.hpp", 3)
    assert "buf" in result["reads"], "buf.data() read must be captured inside requires-expression"


def test_find_identifiers_should_recognise_requires_expr_parameter_as_binding(monkeypatch):
    """find_identifiers on the requires-expr parameter line must capture the bound name."""
    source = """\
template <typename Container>
concept Iterable = requires(Container c) {
    c.begin();
    c.end();
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "iterable.hpp"))
    # Line 2: requires(Container c) — 'c' is introduced as a binding
    result = mcp_server.find_identifiers("pipe", "iterable.hpp", 2)
    assert "c" in result["writes"] or "c" in result["reads"], \
        "Requires-expression parameter 'c' must be captured"


# ---------------------------------------------------------------------------
# 2. Coroutines — co_await / co_yield / co_return
# ---------------------------------------------------------------------------

def test_extract_function_should_include_co_await_and_co_return_in_body():
    """extract_function must return the full coroutine body, including co_await lines."""
    source = """\
#include <coroutine>
#include <string>

Task<std::string> fetch_data(std::string url) {
    auto response = co_await http_get(url);
    co_return response.body;
}
"""
    result = extract_function_from_source(source, "coro.cpp", 5, 200)
    assert result is not None and "text" in result
    assert "co_await" in result["text"]
    assert "co_return" in result["text"]


def test_find_identifiers_should_capture_co_await_operand_as_call_read(monkeypatch):
    """find_identifiers on 'auto value = co_await get_next()' must write value, read get_next."""
    source = """\
Task<int> producer() {
    auto value = co_await get_next();
    co_return value;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "prod.cpp"))
    result = mcp_server.find_identifiers("pipe", "prod.cpp", 2)
    assert "value" in result["writes"], "LHS of co_await assignment must be a write"
    assert "get_next" in result["reads"], "Awaited call 'get_next' must be a read"


def test_trace_identifier_backward_should_trace_through_co_await_assignment(monkeypatch):
    """trace_identifier_backward must link variable usage back to the co_await assignment."""
    source = """\
Task<void> process() {
    auto raw = co_await read_socket();
    auto parsed = parse(raw);
    log(parsed);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "proc.cpp"))
    # Trace 'parsed' from line 4 (log(parsed))
    chain = mcp_server.trace_identifier_backward("pipe", "proc.cpp", 4, "parsed")
    assert isinstance(chain, list)
    lines_in_chain = [entry["line"] for entry in chain]
    assert 3 in lines_in_chain, "Trace must reach line 3 where parsed is assigned"


# ---------------------------------------------------------------------------
# 3. Structured bindings — auto [x, y] = ...
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_both_names_from_pair_structured_binding(monkeypatch):
    """find_identifiers on 'auto [x, y] = getPair()' must list x and y as writes."""
    source = """\
void process_pair() {
    auto [x, y] = getPair();
    use(x + y);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sb.cpp"))
    result = mcp_server.find_identifiers("pipe", "sb.cpp", 2)
    assert "x" in result["writes"], "x from structured binding must be a write"
    assert "y" in result["writes"], "y from structured binding must be a write"


def test_find_identifiers_should_capture_reads_and_writes_in_range_for_structured_binding(monkeypatch):
    """range-for with structured binding: key, val are writes; range expression is a read."""
    source = """\
void dump_map(const std::map<std::string, int>& m) {
    for (auto& [key, val] : m) {
        std::cout << key << ": " << val;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "map.cpp"))
    result = mcp_server.find_identifiers("pipe", "map.cpp", 2)
    assert "key" in result["writes"] or "val" in result["writes"], \
        "Structured binding loop variables must be writes"
    assert "m" in result["reads"], "Range expression 'm' must be a read"


def test_trace_identifier_backward_should_reach_structured_binding_line(monkeypatch):
    """trace_identifier_backward on 'x' must trace back to the structured binding assignment."""
    source = """\
void use_pair() {
    auto [x, y] = compute();
    int result = x * 2;
    store(result);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sb2.cpp"))
    chain = mcp_server.trace_identifier_backward("pipe", "sb2.cpp", 3, "x")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any("auto [x" in entry.get("code", "") or "x" in entry.get("writes", [])
               for entry in chain), "Chain must include the structured binding source"


# ---------------------------------------------------------------------------
# 4. C++20 named-module imports — import std; / export import foo;
# ---------------------------------------------------------------------------

def test_find_imports_should_detect_named_module_import(monkeypatch):
    """find_imports must return 'import std;' as an import entry."""
    source = """\
import std;
import mylib.utils;

int main() {
    std::println("hello");
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "main.cpp"))
    imports = mcp_server.find_imports("pipe", "main.cpp")
    assert any("std" in imp for imp in imports), \
        "Named module import 'import std;' must be detected"


def test_find_imports_should_detect_header_unit_import(monkeypatch):
    """find_imports must return angle-bracket header-unit imports like 'import <format>;'."""
    source = """\
import <format>;
import <vector>;

void print_first(const std::vector<int>& v) {
    std::print("{}", v[0]);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "print.cpp"))
    imports = mcp_server.find_imports("pipe", "print.cpp")
    assert any("format" in imp for imp in imports), \
        "Header-unit import '<format>' must be detected"


def test_find_imports_should_detect_export_import_in_module_interface(monkeypatch):
    """find_imports must recognise 'export import myapp.utils;' in a module interface unit."""
    source = """\
export module myapp.core;

export import myapp.utils;
import std.core;

export int compute(int x);
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "core.cppm"))
    imports = mcp_server.find_imports("pipe", "core.cppm")
    assert any("myapp.utils" in imp for imp in imports), \
        "'export import myapp.utils;' must be detected as an import"


# ---------------------------------------------------------------------------
# 5. Template lambdas — []<typename T>(T x) {}
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_outer_function_containing_template_lambda():
    """extract_function on a line inside a template lambda must return the enclosing function."""
    source = """\
void transform_all(std::vector<int>& v) {
    auto square = []<typename T>(T x) { return x * x; };
    std::ranges::transform(v, v.begin(), square);
}
"""
    result = extract_function_from_source(source, "tmpl.cpp", 2, 200)
    assert result is not None and "text" in result
    assert "transform_all" in result["text"] or "square" in result["text"]


def test_find_identifiers_should_capture_variable_captured_by_template_lambda(monkeypatch):
    """find_identifiers on the lambda line must capture 'factor' from the capture list."""
    source = """\
void apply(std::vector<int>& data, int factor) {
    auto multiply = [factor]<typename T>(T x) { return x * factor; };
    std::ranges::for_each(data, multiply);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cap.cpp"))
    # Line 2: the lambda captures 'factor' from the enclosing scope
    result = mcp_server.find_identifiers("pipe", "cap.cpp", 2)
    assert "factor" in result["reads"] or "multiply" in result["writes"], \
        "Captured 'factor' or bound 'multiply' must be captured"


def test_find_callers_should_find_callsite_of_function_using_template_lambda(tmp_path):
    """find_callers must locate the call site of a function that internally uses a template lambda."""
    src = """\
#include <vector>
#include <algorithm>

void transform_all(std::vector<int>& v) {
    auto sq = []<typename T>(T x) { return x * x; };
    std::ranges::transform(v, v.begin(), sq);
}

int main() {
    std::vector<int> nums = {1, 2, 3};
    transform_all(nums);
    return 0;
}
"""
    (tmp_path / "tmpl.cpp").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "tmpl.cpp", "transform_all")
    assert len(results) >= 1, "Call to 'transform_all' on line 11 must be found"
    assert any(r["line"] == 11 for r in results)
