"""
Additional language construct edge cases not covered by earlier test files.

Covers:
- Go generics (1.18+): func Map[T, U any](...), type constraints
- Python star unpacking: first, *rest = ..., a, *_, b = ...
- JS/TS destructuring with rename and default: { host: dbHost = 'localhost' }
- Ruby blocks: do |x| ... end and { |x| ... } as scope for extract_function
- PHP traits: methods defined in trait, used via 'use Trait'
- Kotlin destructuring: val (a, b) = pair
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.extract import extract_function_from_source


def _stub(source: str, fname: str):
    def _reader(_pid: str, _fp: str):
        return source, Path(fname)
    return _reader


# ===========================================================================
# Go generics (1.18+)
# ===========================================================================

def test_go_generics_extract_function_should_include_type_parameter_in_signature():
    """extract_function must return the full signature including [T, U any] type parameters."""
    source = """\
package slices

func Map[T, U any](slice []T, fn func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}
"""
    result = extract_function_from_source(source, "slices.go", 4, 200)
    assert result is not None and "text" in result
    assert "Map" in result["text"]
    assert "T" in result["text"] or "U" in result["text"], \
        "Type parameters [T, U any] must be present in extracted function"


def test_go_generics_find_identifiers_should_capture_reads_in_generic_function_body(monkeypatch):
    """find_identifiers must capture 'slice' and 'fn' as reads inside a generic function."""
    source = """\
package collections

func Filter[T any](slice []T, predicate func(T) bool) []T {
    var out []T
    for _, v := range slice {
        if predicate(v) {
            out = append(out, v)
        }
    }
    return out
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "collections.go"))
    result = mcp_server.find_identifiers("pipe", "collections.go", 5)
    assert "slice" in result["reads"] or "v" in result["reads"], \
        "Variables in generic function body must be captured as reads"


def test_go_generics_find_callers_should_find_calls_to_generic_function(tmp_path):
    """find_callers must find call sites of a generic function with type parameters."""
    src = """\
package main

func Map[T, U any](slice []T, fn func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}

func main() {
    nums := []int{1, 2, 3}
    doubled := Map(nums, func(n int) int { return n * 2 })
    strs := Map(nums, func(n int) string { return fmt.Sprintf("%d", n) })
    fmt.Println(doubled, strs)
}
"""
    (tmp_path / "main.go").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "main.go", "Map")
    assert len(results) >= 2, "Both calls to generic Map function must be found"


# ===========================================================================
# Python star unpacking
# ===========================================================================

def test_python_star_unpack_should_capture_rest_variable_as_write(monkeypatch):
    """find_identifiers on 'first, *rest = get_items()' must put both first and rest in writes."""
    source = """\
def process_items():
    first, *rest = get_items()
    head, *middle, tail = parse_sequence()
    return process(first, rest)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "processor.py"))
    result = mcp_server.find_identifiers("pipe", "processor.py", 2)
    assert "first" in result["writes"], "first from star-unpack must be a write"
    assert "rest" in result["writes"], "*rest from star-unpack must be a write"


def test_python_star_unpack_should_capture_middle_tail_as_writes(monkeypatch):
    """find_identifiers on 'head, *middle, tail = ...' must capture all three as writes."""
    source = """\
def split_args(args):
    head, *middle, tail = args
    if not middle:
        return head, [], tail
    return head, middle, tail
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "args.py"))
    result = mcp_server.find_identifiers("pipe", "args.py", 2)
    assert "head" in result["writes"], "head from star-unpack must be a write"
    assert "tail" in result["writes"], "tail from star-unpack must be a write"
    assert "middle" in result["writes"] or "args" in result["reads"], \
        "middle or source 'args' must be captured"


def test_python_star_unpack_trace_should_reach_star_assignment(monkeypatch):
    """trace_identifier_backward on 'rest' must trace it to the *rest assignment line."""
    source = """\
def validate_command(raw):
    command, *args = raw.split()
    if not args:
        raise ValueError("Missing arguments")
    return command, args
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "cmd.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "cmd.py", 4, "args")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 2 for entry in chain), \
        "Trace must reach line 2 where *args is bound"


# ===========================================================================
# JS/TS destructuring with rename and default value
# ===========================================================================

def test_ts_destructuring_rename_should_capture_binding_not_key_as_write(monkeypatch):
    """find_identifiers on '{ host: dbHost = "localhost" }' must put dbHost in writes, not host."""
    source = """\
function connectDatabase(config: DatabaseConfig) {
    const { host: dbHost = 'localhost', port: dbPort = 5432, password: dbPass } = config;
    return createConnection(dbHost, dbPort, dbPass);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "db.ts"))
    result = mcp_server.find_identifiers("pipe", "db.ts", 2)
    assert "dbHost" in result["writes"], \
        "Renamed binding 'dbHost' must be a write, not the key 'host'"
    assert "dbPort" in result["writes"], \
        "Renamed binding 'dbPort' must be a write"
    assert "host" not in result["writes"], \
        "Object key 'host' must NOT appear as a write"


def test_ts_destructuring_nested_rename_should_capture_inner_binding(monkeypatch):
    """find_identifiers on nested destructuring with rename must capture inner binding names."""
    source = """\
function extractAuth(req: Request) {
    const { headers: { authorization: authHeader = '' }, user: { id: userId } = {} } = req;
    return { authHeader, userId };
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "auth.ts"))
    result = mcp_server.find_identifiers("pipe", "auth.ts", 2)
    assert "authHeader" in result["writes"] or "userId" in result["writes"], \
        "Inner renamed bindings must appear as writes"
    assert "authorization" not in result["writes"], \
        "Object key 'authorization' must NOT appear as a write"


def test_js_array_destructuring_with_skip_should_capture_only_bound_names(monkeypatch):
    """find_identifiers on '[first, , third] = arr' must capture first and third, not the gap."""
    source = """\
function parseCSVRow(row) {
    const [id, , name, , email] = row.split(',');
    return { id, name, email };
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "csv.js"))
    result = mcp_server.find_identifiers("pipe", "csv.js", 2)
    assert "id" in result["writes"], "id from array destructuring must be a write"
    assert "name" in result["writes"], "name from array destructuring must be a write"
    assert "email" in result["writes"], "email from array destructuring must be a write"


# ===========================================================================
# Ruby blocks as scope for extract_function
# ===========================================================================

def test_ruby_extract_function_should_return_enclosing_method_for_line_in_block():
    """extract_function on a line inside a Ruby do...end block must return the enclosing method."""
    source = """\
def process_users
  User.active.each do |user|
    profile = user.profile
    send_notification(profile.email, "update")
  end
end
"""
    result = extract_function_from_source(source, "processor.rb", 3, 200)
    assert result is not None and "text" in result
    assert "process_users" in result["text"], \
        "Enclosing method 'process_users' must be returned for line inside do...end block"


def test_ruby_find_identifiers_should_capture_block_parameter_as_write(monkeypatch):
    """find_identifiers on 'items.each { |item| ... }' must capture 'item' as a write."""
    source = """\
def calculate_totals(orders)
  orders.each do |order|
    total = order.items.sum(&:price)
    order.update(total: total)
  end
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "calc.rb"))
    result = mcp_server.find_identifiers("pipe", "calc.rb", 2)
    assert "order" in result["writes"] or "orders" in result["reads"], \
        "Block parameter 'order' must be a write or 'orders' a read"


def test_ruby_find_identifiers_should_capture_reads_in_brace_block(monkeypatch):
    """find_identifiers on 'results = items.map { |x| transform(x) }' must capture items as read."""
    source = """\
def transform_all(items)
  results = items.map { |item| normalize(item) }
  results.reject { |r| r.nil? }
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "transform.rb"))
    result = mcp_server.find_identifiers("pipe", "transform.rb", 2)
    assert "results" in result["writes"], "results must be a write"
    assert "items" in result["reads"], "items in .map{} must be a read"


# ===========================================================================
# PHP traits
# ===========================================================================

def test_php_trait_find_callers_should_find_call_to_trait_method(tmp_path):
    """find_callers must find calls to a method defined in a PHP trait."""
    src = """\
<?php

trait Timestampable
{
    public function touch(): void
    {
        $this->updatedAt = new \\DateTime();
    }

    public function getUpdatedAt(): ?\\DateTime
    {
        return $this->updatedAt;
    }
}

class Article
{
    use Timestampable;
}

class Comment
{
    use Timestampable;
}

class ArticleService
{
    public function publish(Article $article): void
    {
        $article->touch();
        $article->published = true;
    }
}
"""
    (tmp_path / "Timestampable.php").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "Timestampable.php", "touch")
    assert len(results) >= 1, "Trait method 'touch' called from ArticleService must be found"


def test_php_trait_find_definition_should_find_method_in_trait(tmp_path):
    """find_definition must locate a method defined inside a trait."""
    src = """\
<?php

trait SoftDeletes
{
    public function delete(): void
    {
        $this->deletedAt = new \\DateTime();
        $this->save();
    }

    public function restore(): void
    {
        $this->deletedAt = null;
        $this->save();
    }

    public function isDeleted(): bool
    {
        return $this->deletedAt !== null;
    }
}
"""
    (tmp_path / "SoftDeletes.php").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "delete")
    assert len(results) >= 1, "Method 'delete' defined in PHP trait must be found"


def test_php_trait_find_imports_should_detect_use_in_class_body(monkeypatch):
    """find_imports must return 'use TraitName' statements inside a PHP class body."""
    source = """\
<?php

namespace App\\Models;

use App\\Traits\\Timestampable;
use App\\Traits\\SoftDeletes;
use App\\Traits\\HasUuid;

class User
{
    use Timestampable, SoftDeletes, HasUuid;

    public function __construct(
        private string $email,
        private string $name,
    ) {}
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "User.php"))
    imports = mcp_server.find_imports("pipe", "User.php")
    assert any("Timestampable" in imp for imp in imports), \
        "use App\\Traits\\Timestampable import must be detected"


# ===========================================================================
# Kotlin destructuring
# ===========================================================================

def test_kotlin_destructuring_should_capture_both_components_as_writes(monkeypatch):
    """find_identifiers on 'val (username, domain) = ...' must put both names in writes."""
    source = """\
fun parseEmail(email: String): Pair<String, String> {
    val (username, domain) = email.split("@").let { it[0] to it[1] }
    return Pair(username, domain)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "email.kt"))
    result = mcp_server.find_identifiers("pipe", "email.kt", 2)
    assert "username" in result["writes"] or "domain" in result["writes"], \
        "Destructured components must be recognised as writes"


def test_kotlin_destructuring_in_for_loop_should_capture_loop_vars(monkeypatch):
    """find_identifiers on 'for ((key, value) in map)' must capture key and value as writes."""
    source = """\
fun printMap(config: Map<String, String>) {
    for ((key, value) in config) {
        println("$key = $value")
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "config.kt"))
    result = mcp_server.find_identifiers("pipe", "config.kt", 2)
    assert "key" in result["writes"] or "value" in result["writes"], \
        "Destructured for-loop variables must be writes"


def test_kotlin_destructuring_trace_should_reach_declaration(monkeypatch):
    """trace_identifier_backward on 'first' must trace it to the destructuring declaration."""
    source = """\
fun processResult(result: Triple<Int, String, Boolean>) {
    val (code, message, success) = result
    if (!success) {
        logError(code, message)
    }
    return code
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "result.kt"))
    chain = mcp_server.trace_identifier_backward("pipe", "result.kt", 4, "code")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 2 for entry in chain), \
        "Trace must reach line 2 where 'code' is bound by destructuring"
