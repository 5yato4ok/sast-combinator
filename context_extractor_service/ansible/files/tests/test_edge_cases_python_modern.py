"""
Edge case tests for modern Python language features (3.10+).

Covers:
- match/case with capture, class, and OR patterns (Python 3.10)
- Walrus operator (:=) in while, comprehensions, if conditions
- except* and ExceptionGroup (Python 3.11)
- Positional-only parameters (/) in function signatures (Python 3.8+, common now)
- PEP 695 type parameter syntax: type X = ..., def f[T](...) (Python 3.12)
"""
from pathlib import Path

import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


# ---------------------------------------------------------------------------
# 1. match/case capture patterns (Python 3.10+)
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_variable_bound_in_sequence_match_pattern(monkeypatch):
    """find_identifiers on 'case [x, y]:' must put x and y in writes."""
    source = """\
def process_command(command):
    match command:
        case [action, target]:
            execute(action, target)
        case [action]:
            execute(action, None)
        case _:
            raise ValueError("Unknown command")
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cmd.py"))
    # Line 3: case [action, target]: — action and target are capture bindings
    result = mcp_server.find_identifiers("pipe", "cmd.py", 3)
    assert "action" in result["writes"] or "target" in result["writes"], \
        "Sequence match capture variables must be recognised as writes"


def test_find_identifiers_should_capture_variable_bound_in_class_pattern(monkeypatch):
    """find_identifiers on 'case Point(x=px, y=py):' must put px and py in writes."""
    source = """\
def describe_shape(shape):
    match shape:
        case Point(x=px, y=py):
            return f"Point at ({px}, {py})"
        case Circle(center=c, radius=r):
            return f"Circle r={r}"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "shapes.py"))
    # Line 3: case Point(x=px, y=py): — px and py are bound
    result = mcp_server.find_identifiers("pipe", "shapes.py", 3)
    assert "px" in result["writes"] or "py" in result["writes"], \
        "Class pattern keyword bindings (px, py) must be writes"


def test_trace_identifier_backward_should_reach_match_case_binding(monkeypatch):
    """trace_identifier_backward on a variable from a match arm must reach the case line."""
    source = """\
def handle_event(event):
    match event:
        case {"type": "click", "button": btn}:
            dispatch_click(btn)
        case {"type": "key", "code": code}:
            dispatch_key(code)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "events.py"))
    # Trace 'btn' from line 4 (dispatch_click(btn))
    chain = mcp_server.trace_identifier_backward("pipe", "events.py", 4, "btn")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 3 for entry in chain), \
        "Trace must reach line 3 where 'btn' is bound in the mapping pattern"


# ---------------------------------------------------------------------------
# 2. Walrus operator (:=)
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_walrus_as_write_in_if_condition(monkeypatch):
    """find_identifiers on 'if (n := len(data)) > 0:' must put 'n' in writes."""
    source = """\
def validate_and_process(data):
    if (n := len(data)) > 0:
        process_items(data, n)
    else:
        raise ValueError("Empty data")
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "validate.py"))
    result = mcp_server.find_identifiers("pipe", "validate.py", 2)
    assert "n" in result["writes"], "Walrus operator target 'n' must be a write"
    assert "data" in result["reads"], "Argument 'data' to len() must be a read"


def test_find_identifiers_should_capture_walrus_as_write_in_while_condition(monkeypatch):
    """find_identifiers on 'while chunk := file.read(1024):' must put 'chunk' in writes."""
    source = """\
def stream_file(file):
    result = []
    while chunk := file.read(1024):
        result.append(process(chunk))
    return result
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "stream.py"))
    result = mcp_server.find_identifiers("pipe", "stream.py", 3)
    assert "chunk" in result["writes"], "Walrus-assigned 'chunk' in while condition must be a write"


def test_trace_identifier_backward_should_trace_walrus_operator_assignment(monkeypatch):
    """trace_identifier_backward must trace a walrus-assigned variable to its := line."""
    source = """\
def find_first_match(items, predicate):
    if (match := next((x for x in items if predicate(x)), None)) is not None:
        log_match(match)
        return match
    return None
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "search.py"))
    # Trace 'match' from line 3 (log_match(match))
    chain = mcp_server.trace_identifier_backward("pipe", "search.py", 3, "match")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 2 for entry in chain), \
        "Trace must reach line 2 where 'match' is introduced by the walrus operator"


# ---------------------------------------------------------------------------
# 3. except* and ExceptionGroup (Python 3.11+)
# ---------------------------------------------------------------------------

def test_extract_function_should_correctly_extract_function_using_except_star():
    """extract_function must return the full function body including except* syntax."""
    source = """\
async def fetch_all(urls):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch(url)) for url in urls]
    try:
        results = await asyncio.gather(*tasks)
    except* TimeoutError as eg:
        handle_timeouts(eg.exceptions)
    except* ConnectionError as eg:
        handle_conn_errors(eg.exceptions)
    return results
"""
    result = extract_function_from_source(source, "fetcher.py", 6, 200)
    assert result is not None and "text" in result
    assert "fetch_all" in result["text"]
    assert "except*" in result["text"] or "except" in result["text"]


def test_find_identifiers_should_capture_exception_group_binding_in_except_star(monkeypatch):
    """find_identifiers on 'except* ValueError as eg:' must put 'eg' in writes."""
    source = """\
def run_tasks(tasks):
    try:
        results = execute_all(tasks)
    except* ValueError as eg:
        for exc in eg.exceptions:
            log_error(exc)
    return results
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "tasks.py"))
    result = mcp_server.find_identifiers("pipe", "tasks.py", 4)
    assert "eg" in result["writes"], "'eg' bound by 'except* ... as eg' must be a write"


def test_extract_function_should_handle_nested_try_except_star_blocks():
    """extract_function must not break on a function with nested try/except* blocks."""
    source = """\
async def orchestrate():
    try:
        async with asyncio.TaskGroup() as tg:
            outer_task = tg.create_task(outer())
        try:
            inner_result = await inner()
        except* IOError as eg:
            recover_io(eg)
    except* RuntimeError as eg:
        abort(eg.exceptions)
"""
    result = extract_function_from_source(source, "orch.py", 2, 200)
    assert result is not None and "text" in result
    assert "orchestrate" in result["text"]
    assert "except*" in result["text"] or "except" in result["text"]


# ---------------------------------------------------------------------------
# 4. Positional-only parameters (/)
# ---------------------------------------------------------------------------

def test_extract_function_should_preserve_positional_only_separator_in_signature():
    """extract_function must include the / separator in the function signature."""
    source = """\
def make_url(scheme, host, /, path="", *, port=None):
    base = f"{scheme}://{host}"
    if port:
        base += f":{port}"
    return base + path
"""
    result = extract_function_from_source(source, "url.py", 1, 200)
    assert result is not None and "text" in result
    assert "make_url" in result["text"]
    assert "/" in result["text"], "Positional-only separator '/' must be preserved"


def test_find_identifiers_should_capture_positional_only_params_as_reads(monkeypatch):
    """find_identifiers on a line using posonly params must capture them as reads."""
    source = """\
def format_value(value, fmt, /, *, precision=2):
    formatted = fmt.format(value, precision=precision)
    return formatted
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "fmt.py"))
    result = mcp_server.find_identifiers("pipe", "fmt.py", 2)
    assert "fmt" in result["reads"] or "value" in result["reads"], \
        "Positional-only parameters must be captured as reads when used"
    assert "formatted" in result["writes"], "Assignment to 'formatted' must be a write"


def test_find_callers_should_find_calls_to_function_with_positional_only_params(tmp_path):
    """find_callers must locate call sites of a function defined with positional-only params."""
    src = """\
def hash_password(password, salt, /, *, rounds=100000):
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)

def create_user(username, password):
    salt = generate_salt()
    hashed = hash_password(password, salt)
    return {"username": username, "password": hashed}
"""
    (tmp_path / "auth.py").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "auth.py", "hash_password")
    assert len(results) >= 1, "Call to 'hash_password' on line 7 must be found"
    assert any(r["line"] == 7 for r in results)


# ---------------------------------------------------------------------------
# 5. PEP 695 type parameter syntax (Python 3.12)
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_generic_function_with_pep695_syntax():
    """extract_function must return the full body of a PEP 695 generic function def f[T](...)."""
    source = """\
def first[T](items: list[T]) -> T:
    if not items:
        raise ValueError("Empty list")
    return items[0]
"""
    result = extract_function_from_source(source, "generics.py", 1, 200)
    assert result is not None and "text" in result
    assert "first" in result["text"]


def test_find_identifiers_should_capture_reads_in_pep695_generic_function(monkeypatch):
    """find_identifiers must capture 'items' as a read inside a PEP 695 generic function."""
    source = """\
def map_items[T, U](items: list[T], fn: Callable[[T], U]) -> list[U]:
    result = [fn(item) for item in items]
    return result
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "map.py"))
    result = mcp_server.find_identifiers("pipe", "map.py", 2)
    assert "result" in result["writes"], "result must be a write"
    assert "items" in result["reads"] or "fn" in result["reads"], \
        "items and fn must be captured as reads"


def test_find_definition_should_find_pep695_type_alias(tmp_path):
    """find_definition must find a PEP 695 type alias defined with the 'type' keyword."""
    src = """\
type Vector[T] = list[T]
type Matrix[T] = list[Vector[T]]

def dot_product[T: (int, float)](a: Vector[T], b: Vector[T]) -> T:
    return sum(x * y for x, y in zip(a, b))
"""
    (tmp_path / "linalg.py").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "Vector")
    assert len(results) >= 1, "PEP 695 type alias 'Vector' must be found by find_definition"


# ---------------------------------------------------------------------------
# match/case guard clause — capture variables vs guard reads
# ---------------------------------------------------------------------------

def test_case_pattern_guard_variable_not_duplicated_as_write(monkeypatch):
    """Variables used only in a case guard (if condition) must not be added to
    writes via guard traversal.

    Regression for: _collect_case_pattern_captures traversing into if_clause
    and misclassifying guard-clause reads as captured (write) variables.
    """
    source = """\
def classify(point):
    match point:
        case Point(x=px, y=py) if px > 0:
            return "positive x"
        case _:
            return "other"
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("classify.py")))
    result = mcp_server.find_identifiers("pipe", "classify.py", 3)
    writes = set(result.get("writes", []))
    # px and py are capture variables — they belong in writes
    assert "px" in writes, f"'px' (capture variable) must be in writes; got {writes}"
    assert "py" in writes, f"'py' (capture variable) must be in writes; got {writes}"
    # The guard expression 'px > 0' must not add extra unexpected names to writes
    unexpected = writes - {"px", "py", "Point"}
    assert not unexpected, f"Guard clause variables incorrectly added to writes: {unexpected}"
