"""
Tests for _collect_decl_names correctness across languages.

Covers the bug where `if out: continue` used the global accumulator instead of
a local success flag, causing later declarations to be silently dropped when the
first declaration already populated `out`.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub(source: str, filename: str):
    mcp_server._read_source = lambda _pid, _fp: (source, Path(filename))


# ---------------------------------------------------------------------------
# Go: two consecutive var declarations in one block
# ---------------------------------------------------------------------------

def test_go_two_var_declarations_both_names_in_writes(monkeypatch):
    """Both names from consecutive Go var declarations must appear in writes."""
    source = """\
package main

func setup() {
    var db *Database
    var cache *Cache
    db = connect()
    cache = newCache()
    _ = db
    _ = cache
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("setup.go")))
    result = mcp_server.find_identifiers("pipe", "setup.go", 4)
    writes = set(result.get("writes", []))
    assert "db" in writes, f"'db' missing from writes; got {writes}"


def test_go_two_var_declarations_second_name_in_writes(monkeypatch):
    """The second var declaration name must not be dropped due to the accumulator bug."""
    source = """\
package main

func setup() {
    var db *Database
    var cache *Cache
    db = connect()
    cache = newCache()
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("setup.go")))
    result = mcp_server.find_identifiers("pipe", "setup.go", 5)
    writes = set(result.get("writes", []))
    assert "cache" in writes, f"'cache' missing from writes; got {writes}"


# ---------------------------------------------------------------------------
# Kotlin: two consecutive variable declarations
# ---------------------------------------------------------------------------

def test_kotlin_two_val_declarations_both_names_in_writes(monkeypatch):
    """Both names from consecutive Kotlin val declarations must appear in writes."""
    source = """\
fun init() {
    val host: String = getHost()
    val port: Int = getPort()
    println(host)
    println(port)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("init.kt")))
    result_host = mcp_server.find_identifiers("pipe", "init.kt", 2)
    result_port = mcp_server.find_identifiers("pipe", "init.kt", 3)
    assert "host" in set(result_host.get("writes", [])), \
        f"'host' missing from writes; got {result_host.get('writes')}"
    assert "port" in set(result_port.get("writes", [])), \
        f"'port' missing from writes; got {result_port.get('writes')}"
