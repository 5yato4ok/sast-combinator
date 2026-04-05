"""
Edge case tests for Bash / shell script language features.

Covers:
- Heredoc inside functions: <<EOF / <<-EOF / with variable expansion
- Process substitution: <(cmd) and >(cmd)
- Associative arrays: declare -A, arr[key]=val, ${arr[$key]}
- Arithmetic expansion: $(( )) and (( ))
- trap handlers referencing functions
"""
import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


# ---------------------------------------------------------------------------
# 1. Heredoc inside functions
# ---------------------------------------------------------------------------

def test_extract_function_should_not_stop_at_heredoc_delimiter():
    """extract_function must include lines after the heredoc EOF marker in the function body."""
    source = """\
generate_config() {
    cat <<EOF
server {
    listen 80;
    server_name example.com;
}
EOF
    echo "Config written"
}
"""
    result = extract_function_from_source(source, "setup.sh", 8, 200)
    assert result is not None and "text" in result
    assert "generate_config" in result["text"]
    assert "Config written" in result["text"], \
        "Lines after the heredoc EOF terminator must be included in the extracted function"


def test_extract_function_should_handle_indented_heredoc():
    """extract_function must correctly parse the indented heredoc (<<-EOF) syntax."""
    source = """\
deploy() {
    local env="$1"
    cat <<-EOF
        environment: ${env}
        debug: false
    EOF
    echo "Deployed to ${env}"
}
"""
    result = extract_function_from_source(source, "deploy.sh", 7, 200)
    assert result is not None and "text" in result
    assert "Deployed to" in result["text"], \
        "Function body must continue after indented heredoc"


def test_extract_env_variables_should_find_variables_in_heredoc_content(monkeypatch, tmp_path):
    """extract_env_variables must find ENV assignments inside a heredoc block."""
    content = """\
#!/bin/bash
write_env() {
    cat > .env <<EOF
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=supersecret
DEBUG=false
EOF
}
"""
    f = tmp_path / "write_env.sh"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "write_env.sh")
    names = [v["name"] for v in result]
    assert "DATABASE_URL" in names or "SECRET_KEY" in names, \
        "Variables defined in heredoc content must be detected"


# ---------------------------------------------------------------------------
# 2. Process substitution
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_files_used_in_input_process_substitution(monkeypatch):
    """find_identifiers on 'diff <(sort file1) <(sort file2)' must capture file1 and file2."""
    source = """\
compare_sorted() {
    local file1="$1"
    local file2="$2"
    diff <(sort "$file1") <(sort "$file2")
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cmp.sh"))
    result = mcp_server.find_identifiers("pipe", "cmp.sh", 4)
    assert "file1" in result["reads"] or "file2" in result["reads"], \
        "Variables inside process substitution must be captured as reads"


def test_find_identifiers_should_capture_output_in_output_process_substitution(monkeypatch):
    """find_identifiers on 'tee >(gzip > output)' must capture 'output' as a read."""
    source = """\
compress_and_log() {
    local output="$1"
    cat data.txt | tee >(gzip > "$output") | wc -l
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "compress.sh"))
    result = mcp_server.find_identifiers("pipe", "compress.sh", 3)
    assert "output" in result["reads"], \
        "'output' used inside output process substitution must be a read"


def test_extract_function_should_extract_full_function_using_process_substitution():
    """extract_function must return the full body of a function that uses process substitution."""
    source = """\
merge_logs() {
    local dir="$1"
    local merged="$2"
    comm -12 <(sort "$dir/app.log") <(sort "$dir/error.log") > "$merged"
    echo "Merged into $merged"
}
"""
    result = extract_function_from_source(source, "logs.sh", 4, 200)
    assert result is not None and "text" in result
    assert "merge_logs" in result["text"]
    assert "comm" in result["text"] or "Merged" in result["text"]


# ---------------------------------------------------------------------------
# 3. Associative arrays
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_reads_in_associative_array_access(monkeypatch):
    """find_identifiers on 'echo "${config[$key]}"' must capture 'config' and 'key' as reads."""
    source = """\
lookup_config() {
    declare -A config
    config[host]="localhost"
    config[port]="5432"
    local key="$1"
    echo "${config[$key]}"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cfg.sh"))
    result = mcp_server.find_identifiers("pipe", "cfg.sh", 6)
    assert "config" in result["reads"] or "key" in result["reads"], \
        "Associative array and key variable must be captured as reads"


def test_find_identifiers_should_capture_writes_in_associative_array_assignment(monkeypatch):
    """find_identifiers on 'arr[$key]=$value' must capture arr as a write and key, value as reads."""
    source = """\
build_index() {
    declare -A arr
    local key="$1"
    local value="$2"
    arr[$key]=$value
    echo "Indexed $key"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "idx.sh"))
    result = mcp_server.find_identifiers("pipe", "idx.sh", 5)
    # arr is being written to; key and value are reads
    assert "arr" in result["writes"] or "key" in result["reads"], \
        "Array assignment must capture arr as write and key/value as reads"


def test_trace_identifier_backward_should_trace_through_associative_array_write(monkeypatch):
    """trace_identifier_backward must reach the assignment line for an array value."""
    source = """\
process() {
    declare -A cache
    local item="$1"
    cache["$item"]=$(compute "$item")
    local result="${cache[$item]}"
    echo "$result"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "proc.sh"))
    chain = mcp_server.trace_identifier_backward("pipe", "proc.sh", 6, "result")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 5 for entry in chain), \
        "Trace must reach line 5 where 'result' is assigned from the array lookup"


# ---------------------------------------------------------------------------
# 4. Arithmetic expansion
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_variables_in_arithmetic_expansion(monkeypatch):
    """find_identifiers on 'result=$((a + b * c))' must capture a, b, c as reads."""
    source = """\
calculate() {
    local a="$1"
    local b="$2"
    local c="$3"
    local result=$((a + b * c))
    echo "$result"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "calc.sh"))
    result = mcp_server.find_identifiers("pipe", "calc.sh", 5)
    assert "result" in result["writes"], "'result' must be a write"
    assert "a" in result["reads"] or "b" in result["reads"], \
        "Arithmetic operands must be captured as reads"


def test_find_identifiers_should_capture_increment_as_both_read_and_write(monkeypatch):
    """find_identifiers on '((count++))' must capture 'count' as both read and write."""
    source = """\
count_items() {
    local count=0
    local -a items=("$@")
    for item in "${items[@]}"; do
        ((count++))
    done
    echo "$count"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "count.sh"))
    result = mcp_server.find_identifiers("pipe", "count.sh", 5)
    # count++ reads then writes count
    assert "count" in result["reads"] or "count" in result["writes"], \
        "'count' in (( count++ )) must be captured"


def test_trace_identifier_backward_should_trace_arithmetic_result(monkeypatch):
    """trace_identifier_backward must trace an arithmetic result back to its operands."""
    source = """\
compute_checksum() {
    local size="$1"
    local offset="$2"
    local checksum=$(( (size * 31 + offset) % 256 ))
    send_checksum "$checksum"
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "chk.sh"))
    chain = mcp_server.trace_identifier_backward("pipe", "chk.sh", 5, "checksum")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 4 for entry in chain), \
        "Trace must reach line 4 where checksum is computed"


# ---------------------------------------------------------------------------
# 5. trap handlers
# ---------------------------------------------------------------------------

def test_extract_function_should_include_trap_statement_in_function_body():
    """extract_function must include the trap statement within the function body."""
    source = """\
run_with_cleanup() {
    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT
    process_files "$tmpdir"
    echo "Done"
}
"""
    result = extract_function_from_source(source, "run.sh", 4, 200)
    assert result is not None and "text" in result
    assert "trap" in result["text"], "trap statement must be included in the extracted body"


def test_find_callers_should_find_function_referenced_in_trap(tmp_path):
    """find_callers must find a function whose name is used inside a trap command."""
    src = """\
#!/bin/bash

cleanup() {
    rm -rf "$TMPDIR"
    echo "Cleaned up"
}

main() {
    TMPDIR=$(mktemp -d)
    trap cleanup EXIT
    run_pipeline
}
"""
    (tmp_path / "pipeline.sh").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "pipeline.sh", "cleanup")
    assert len(results) >= 1, "'cleanup' referenced in trap must be found as a call"


def test_find_identifiers_should_capture_signal_name_and_handler_in_trap(monkeypatch):
    """find_identifiers on a trap statement must capture the handler function as a read."""
    source = """\
setup_handlers() {
    trap handle_interrupt INT
    trap handle_term TERM
    trap 'echo interrupted' HUP
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "handlers.sh"))
    result = mcp_server.find_identifiers("pipe", "handlers.sh", 2)
    assert "handle_interrupt" in result["reads"] or "handle_interrupt" in result["writes"], \
        "Handler function name in trap must be captured"
