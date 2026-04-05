"""
Edge case tests for modern TypeScript language features.

Covers:
- Stage-3 decorators: class, method, and accessor decorators
- `using` / `await using` declarations (TC39 explicit resource management)
- `satisfies` operator
- Template literal types in function signatures and type aliases
- `const` type parameters (TypeScript 5.0)
"""
import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


# ---------------------------------------------------------------------------
# 1. Stage-3 decorators
# ---------------------------------------------------------------------------

def test_find_decorators_should_find_class_decorator_with_arguments(monkeypatch):
    """find_decorators must return a class-level decorator with its arguments."""
    source = """\
@Injectable({ providedIn: 'root' })
export class UserService {
    constructor(private http: HttpClient) {}

    getUser(id: string) {
        return this.http.get(`/users/${id}`);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "user.service.ts"))
    result = mcp_server.find_decorators("pipe", "user.service.ts", 5)
    assert any("Injectable" in d for d in result), \
        "Class decorator @Injectable must be returned for a method inside the class"


def test_find_decorators_should_find_method_level_decorator(monkeypatch):
    """find_decorators must return a method-level decorator."""
    source = """\
export class Controller {
    @Get('/users')
    @UseGuards(AuthGuard)
    async listUsers(): Promise<User[]> {
        return this.service.findAll();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ctrl.ts"))
    result = mcp_server.find_decorators("pipe", "ctrl.ts", 4)
    assert any("Get" in d for d in result), "@Get decorator must be found on the method"
    assert any("UseGuards" in d for d in result), "@UseGuards decorator must be found on the method"


def test_find_decorators_should_find_accessor_decorator_on_getter(monkeypatch):
    """find_decorators must detect a decorator placed on an accessor (get/set)."""
    source = """\
export class Model {
    private _name: string = '';

    @Validate
    get name(): string {
        return this._name;
    }

    set name(value: string) {
        this._name = value;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "model.ts"))
    result = mcp_server.find_decorators("pipe", "model.ts", 5)
    assert any("Validate" in d for d in result), "@Validate accessor decorator must be found"


# ---------------------------------------------------------------------------
# 2. `using` / `await using` declarations
# ---------------------------------------------------------------------------

def test_find_identifiers_should_treat_using_declaration_as_write(monkeypatch):
    """`using resource = openFile(path)` must put 'resource' in writes."""
    source = """\
async function processFile(path: string): Promise<void> {
    using resource = openFile(path);
    const data = resource.read();
    process(data);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "file.ts"))
    result = mcp_server.find_identifiers("pipe", "file.ts", 2)
    assert "resource" in result["writes"], \
        "'using' declaration must be recognised as a write (variable binding)"


def test_find_identifiers_should_treat_await_using_as_write(monkeypatch):
    """`await using conn = getConnection()` must put 'conn' in writes."""
    source = """\
async function query(sql: string): Promise<Row[]> {
    await using conn = await getConnection();
    return await conn.execute(sql);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "db.ts"))
    result = mcp_server.find_identifiers("pipe", "db.ts", 2)
    assert "conn" in result["writes"], \
        "'await using' declaration must be recognised as a write"


def test_trace_identifier_backward_should_trace_using_bound_variable(monkeypatch):
    """trace_identifier_backward must trace a variable introduced by `using` back to its declaration."""
    source = """\
async function readConfig(path: string) {
    await using file = await openAsync(path);
    const raw = await file.readAll();
    return JSON.parse(raw);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cfg.ts"))
    # Trace 'file' from line 3 (file.readAll())
    chain = mcp_server.trace_identifier_backward("pipe", "cfg.ts", 3, "file")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 2 for entry in chain), \
        "Trace must reach the 'await using file' declaration on line 2"


# ---------------------------------------------------------------------------
# 3. `satisfies` operator
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_satisfies_lhs_as_write(monkeypatch):
    """`const config = {...} satisfies Config` must put 'config' in writes."""
    source = """\
function createConfig() {
    const config = {
        host: 'localhost',
        port: 5432,
    } satisfies DatabaseConfig;
    return config;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "config.ts"))
    result = mcp_server.find_identifiers("pipe", "config.ts", 2)
    assert "config" in result["writes"], \
        "Variable on the LHS of a satisfies expression must be a write"


def test_trace_identifier_backward_should_trace_through_satisfies_expression(monkeypatch):
    """trace_identifier_backward must link usage of 'config' back through 'satisfies' to the literal."""
    source = """\
function bootstrap() {
    const cfg = {
        apiKey: process.env.API_KEY,
        timeout: 3000,
    } satisfies AppConfig;
    startApp(cfg);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "boot.ts"))
    chain = mcp_server.trace_identifier_backward("pipe", "boot.ts", 6, "cfg")
    assert isinstance(chain, list) and len(chain) >= 1
    # Should trace back to the object literal assignment
    assert any(entry["line"] in range(2, 6) for entry in chain)


def test_extract_function_should_include_satisfies_expression_in_body():
    """extract_function must include the full function body when it uses satisfies."""
    source = """\
export function getSettings(): AppSettings {
    const settings = {
        debug: false,
        logLevel: 'warn',
    } satisfies AppSettings;
    return settings;
}
"""
    result = extract_function_from_source(source, "settings.ts", 2, 200)
    assert result is not None and "text" in result
    assert "satisfies" in result["text"], "satisfies keyword must be preserved in extracted body"


# ---------------------------------------------------------------------------
# 4. Template literal types
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_function_with_template_literal_type_return():
    """extract_function must correctly extract a function whose return type is a template literal type."""
    source = """\
type EventName<T extends string> = `on${Capitalize<T>}`;

function getHandler<T extends string>(event: T): EventName<T> {
    return `on${event.charAt(0).toUpperCase()}${event.slice(1)}` as EventName<T>;
}
"""
    result = extract_function_from_source(source, "events.ts", 3, 200)
    assert result is not None and "text" in result
    assert "getHandler" in result["text"]


def test_find_identifiers_should_capture_reads_in_template_literal_type_usage(monkeypatch):
    """find_identifiers must capture 'event' and 'handler' reads inside a template literal expression."""
    source = """\
function dispatchEvent<T extends string>(event: T, handler: EventHandler<T>): void {
    const key: `${T}_handler` = `${event}_handler`;
    registry.set(key, handler);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "dispatch.ts"))
    result = mcp_server.find_identifiers("pipe", "dispatch.ts", 2)
    assert "key" in result["writes"], "LHS 'key' must be a write"
    assert "event" in result["reads"], "'event' inside template literal must be a read"


def test_find_definition_should_find_template_literal_type_alias(tmp_path):
    """find_definition must find a type alias defined as a template literal type."""
    src = """\
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';
type Endpoint<M extends HttpMethod> = `${Lowercase<M>}:${string}`;

function register<M extends HttpMethod>(endpoint: Endpoint<M>, handler: () => void): void {
    routes.set(endpoint, handler);
}
"""
    (tmp_path / "routes.ts").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "Endpoint")
    assert len(results) >= 1, "Template literal type alias 'Endpoint' must be found"


# ---------------------------------------------------------------------------
# 5. `const` type parameters (TypeScript 5.0)
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_function_with_const_type_parameter():
    """extract_function must correctly extract a function declared with <const T>."""
    source = """\
function identity<const T>(value: T): T {
    return value;
}

function firstElement<const T extends readonly unknown[]>(arr: T): T[0] {
    return arr[0];
}
"""
    result = extract_function_from_source(source, "generics.ts", 5, 200)
    assert result is not None and "text" in result
    assert "firstElement" in result["text"]
    assert "const T" in result["text"] or "const" in result["text"]


def test_find_identifiers_should_capture_reads_in_const_type_param_function(monkeypatch):
    """find_identifiers must capture 'arr' as read inside a `const T` generic function body."""
    source = """\
function toTuple<const T extends readonly unknown[]>(...args: T): T {
    return args as T;
}

function pick<const T extends object, const K extends keyof T>(obj: T, key: K): T[K] {
    return obj[key];
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "utils.ts"))
    result = mcp_server.find_identifiers("pipe", "utils.ts", 6)
    assert "obj" in result["reads"], "'obj' must be captured as a read"
    assert "key" in result["reads"], "'key' must be captured as a read"


def test_find_callers_should_find_calls_to_function_with_const_type_parameter(tmp_path):
    """find_callers must find all call sites of a function with a const type parameter."""
    src = """\
function identity<const T>(value: T): T {
    return value;
}

const a = identity(42);
const b = identity('hello');
const c = identity([1, 2, 3]);
"""
    (tmp_path / "id.ts").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "id.ts", "identity")
    assert len(results) >= 3, "All 3 call sites of 'identity' must be found"
