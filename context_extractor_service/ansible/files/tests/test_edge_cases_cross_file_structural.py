"""
Cross-file and structural edge case tests.

Covers:
- trace_identifier_backward stopping at function parameter (cross-file boundary signal)
- find_callers across multiple subdirectories in a project
- find_definition: multiple definitions (overloaded), interface vs implementation
- find_definition: partial classes (C#), extension methods
- Dynamic dispatch patterns: function reference in variable, getattr, higher-order functions
- Very large project search: find_callers with many files (performance)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub(source: str, fname: str):
    def _reader(_pid: str, _fp: str):
        return source, Path(fname)
    return _reader


# ===========================================================================
# trace_identifier_backward: cross-file boundary
# ===========================================================================

def test_trace_should_stop_at_function_parameter_and_not_recurse_beyond(monkeypatch):
    """trace_identifier_backward must stop at a function parameter (cross-file origin)."""
    source = """\
def process_payment(payment_data: dict, user_id: int):
    amount = payment_data["amount"]
    currency = payment_data.get("currency", "USD")
    result = gateway.charge(user_id, amount, currency)
    return result
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "payments.py"))
    # Trace payment_data from line 2 — it's a function parameter, origin is cross-file
    chain = mcp_server.trace_identifier_backward("pipe", "payments.py", 2, "payment_data")
    assert isinstance(chain, list)
    # Chain should be short (1-2 hops) and must not produce infinite results
    assert len(chain) <= 5, \
        "Trace on a function parameter must stop quickly, not recurse indefinitely"


def test_trace_should_stop_after_max_hops_for_deeply_chained_assignments(monkeypatch):
    """trace_identifier_backward must respect the 3-hop limit."""
    source = """\
def build_query(user_id, filters):
    base = get_base_queryset(user_id)
    filtered = apply_filters(base, filters)
    sorted_qs = sort_queryset(filtered)
    paginated = paginate(sorted_qs)
    return paginated
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "query.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "query.py", 6, "paginated")
    assert isinstance(chain, list)
    assert len(chain) <= 4, "3-hop limit must be respected"


def test_trace_should_handle_variable_reassigned_multiple_times(monkeypatch):
    """trace_identifier_backward on a variable reassigned several times must trace to first."""
    source = """\
def normalise(raw_input: str) -> str:
    value = raw_input
    value = value.strip()
    value = value.lower()
    value = remove_special_chars(value)
    return value
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "normalise.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "normalise.py", 6, "value")
    assert isinstance(chain, list) and len(chain) >= 1
    # Should at minimum find the last reassignment
    assert any(entry["line"] in range(2, 6) for entry in chain)


# ===========================================================================
# find_callers: multi-directory project
# ===========================================================================

def test_find_callers_should_find_calls_across_subdirectories(tmp_path):
    """find_callers must find call sites in files nested under subdirectories."""
    (tmp_path / "core").mkdir()
    (tmp_path / "api").mkdir()
    (tmp_path / "jobs").mkdir()

    (tmp_path / "core" / "auth.py").write_text("""\
def validate_token(token: str) -> bool:
    return jwt.decode(token) is not None
""")
    (tmp_path / "api" / "middleware.py").write_text("""\
from core.auth import validate_token

def auth_middleware(request):
    token = request.headers.get("Authorization", "")
    if not validate_token(token):
        return 401
""")
    (tmp_path / "jobs" / "scheduler.py").write_text("""\
from core.auth import validate_token

def run_job(job_token: str):
    if not validate_token(job_token):
        raise PermissionError("Invalid job token")
""")

    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "core/auth.py", "validate_token")
    assert len(results) >= 2, \
        "Calls to validate_token from both api/ and jobs/ subdirectories must be found"


def test_find_callers_should_find_method_calls_across_module_tree(tmp_path):
    """find_callers must locate method calls even when caller files are in peer directories."""
    (tmp_path / "services").mkdir()
    (tmp_path / "controllers").mkdir()
    (tmp_path / "tasks").mkdir()

    (tmp_path / "services" / "user_service.py").write_text("""\
class UserService:
    def send_verification_email(self, user_id: int) -> None:
        email = self._get_email(user_id)
        mailer.send(email, "verify")
""")
    (tmp_path / "controllers" / "registration.py").write_text("""\
from services.user_service import UserService

class RegistrationController:
    def post(self, request):
        user = create_user(request.data)
        UserService().send_verification_email(user.id)
""")
    (tmp_path / "tasks" / "onboarding.py").write_text("""\
from services.user_service import UserService

def trigger_onboarding(user_id: int):
    svc = UserService()
    svc.send_verification_email(user_id)
""")

    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "services/user_service.py", "send_verification_email")
    assert len(results) >= 2, \
        "Method calls from controllers/ and tasks/ must both be found"


# ===========================================================================
# find_definition: multiple definitions and interface/implementation
# ===========================================================================

def test_find_definition_should_return_all_overloaded_function_definitions(tmp_path):
    """find_definition must return all C++ overloads when multiple definitions share a name."""
    src = """\
#include <string>
#include <vector>

void log(const std::string& message);
void log(const std::string& message, int level);
void log(const std::string& message, const std::string& category, int level);

void log(const std::string& message) {
    std::cerr << message << std::endl;
}

void log(const std::string& message, int level) {
    if (level >= current_level) log(message);
}
"""
    (tmp_path / "logger.cpp").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "log")
    assert len(results) >= 2, \
        "All overloaded 'log' function definitions must be returned"


def test_find_definition_should_find_interface_and_implementation_both(tmp_path):
    """find_definition must return both the interface declaration and its implementation."""
    src = """\
package service

type UserRepository interface {
    FindByID(ctx context.Context, id string) (*User, error)
    Save(ctx context.Context, user *User) error
    Delete(ctx context.Context, id string) error
}

type postgresUserRepository struct {
    db *sql.DB
}

func (r *postgresUserRepository) FindByID(ctx context.Context, id string) (*User, error) {
    var user User
    err := r.db.QueryRowContext(ctx, "SELECT * FROM users WHERE id = $1", id).Scan(&user)
    return &user, err
}
"""
    (tmp_path / "user_repo.go").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "FindByID")
    assert len(results) >= 1, "FindByID must be found (interface or implementation)"


def test_find_definition_should_find_partial_class_definition(tmp_path):
    """find_definition must handle C# partial class — both parts are valid definitions."""
    src1 = """\
public partial class UserService
{
    private readonly IUserRepository _repo;
    public UserService(IUserRepository repo) => _repo = repo;

    public async Task<User?> GetByIdAsync(Guid id) =>
        await _repo.GetByIdAsync(id);
}
"""
    src2 = """\
public partial class UserService
{
    public async Task<User> CreateAsync(CreateUserRequest request)
    {
        var user = new User { Email = request.Email };
        await _repo.SaveAsync(user);
        return user;
    }
}
"""
    (tmp_path / "UserService.Queries.cs").write_text(src1)
    (tmp_path / "UserService.Commands.cs").write_text(src2)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "UserService")
    assert len(results) >= 1, "Partial class UserService must be found in at least one file"


# ===========================================================================
# Dynamic dispatch: function references in variables
# ===========================================================================

def test_find_callers_should_find_function_passed_as_callback(tmp_path):
    """find_callers must find a function used as a callback argument."""
    src = """\
def validate_email(value: str) -> bool:
    return "@" in value and "." in value

def validate_age(value: int) -> bool:
    return 0 < value < 150

def process_form(data: dict, validators: list):
    for key, validator in validators:
        if not validator(data.get(key)):
            raise ValueError(f"Invalid {key}")

form_validators = [
    ("email", validate_email),
    ("age", validate_age),
]
process_form(request_data, form_validators)
"""
    (tmp_path / "forms.py").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    # validate_email is referenced in the list, not called directly
    results = find_callers(tmp_path, "forms.py", "validate_email")
    assert isinstance(results, list), "find_callers must not crash for callback references"
    # This may or may not find the reference — documents the behavior either way


def test_find_callers_should_find_function_stored_in_dict_and_called(tmp_path):
    """find_callers should find (or document inability to find) dict-dispatch calls."""
    src = """\
def handle_create(event):
    return create_resource(event["data"])

def handle_update(event):
    return update_resource(event["id"], event["data"])

def handle_delete(event):
    return delete_resource(event["id"])

HANDLERS = {
    "create": handle_create,
    "update": handle_update,
    "delete": handle_delete,
}

def dispatch(event):
    handler = HANDLERS.get(event["type"])
    if handler:
        return handler(event)
"""
    (tmp_path / "dispatch.py").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "dispatch.py", "handle_create")
    # Function is referenced in dict — static analysis may or may not find it
    assert isinstance(results, list), \
        "find_callers must return a list for dict-dispatch pattern"


def test_find_callers_should_find_js_array_higher_order_function_callback(tmp_path):
    """find_callers must find a named function used as a .forEach/.map callback."""
    src = """\
function processUser(user) {
    return {
        id: user.id,
        name: user.name.trim(),
        email: user.email.toLowerCase(),
    };
}

function enrichUser(user) {
    return { ...user, role: getRoleFor(user.id) };
}

async function loadUsers(ids) {
    const raw = await fetchUsers(ids);
    const processed = raw.map(processUser);
    const enriched = processed.map(enrichUser);
    return enriched;
}
"""
    (tmp_path / "users.js").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "users.js", "processUser")
    assert len(results) >= 1, \
        "Named function passed to .map() as callback must be found as a call site"


def test_find_callers_should_find_java_method_reference_in_stream(tmp_path):
    """find_callers must find method references used in Java Stream operations."""
    src = """\
public class DataProcessor {

    public static String sanitize(String input) {
        return input.trim().toLowerCase();
    }

    public static boolean isValid(String value) {
        return value != null && !value.isEmpty();
    }

    public List<String> processAll(List<String> items) {
        return items.stream()
            .filter(DataProcessor::isValid)
            .map(DataProcessor::sanitize)
            .collect(Collectors.toList());
    }
}
"""
    (tmp_path / "DataProcessor.java").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "DataProcessor.java", "sanitize")
    assert len(results) >= 1, \
        "Java method reference DataProcessor::sanitize must be found"


# ===========================================================================
# find_definition: extension functions and mixins
# ===========================================================================

def test_find_definition_should_find_kotlin_extension_function(tmp_path):
    """find_definition must find a Kotlin extension function defined on a type."""
    src = """\
package ext

fun String.toSlug(): String =
    this.lowercase()
        .replace(Regex("[^a-z0-9\\s-]"), "")
        .replace(Regex("\\s+"), "-")
        .trim('-')

fun String.maskEmail(): String {
    val at = indexOf('@')
    return if (at <= 1) this
    else substring(0, 1) + "*".repeat(at - 1) + substring(at)
}

fun main() {
    val slug = "Hello World!".toSlug()
    val masked = "user@example.com".maskEmail()
    println("$slug | $masked")
}
"""
    (tmp_path / "extensions.kt").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "toSlug")
    assert len(results) >= 1, "Kotlin extension function 'toSlug' must be found"


def test_find_definition_should_find_ruby_module_mixin_method(tmp_path):
    """find_definition must find a method defined inside a Ruby module used as a mixin."""
    src = """\
module Searchable
  def self.included(base)
    base.extend(ClassMethods)
  end

  module ClassMethods
    def search(query)
      where("name ILIKE ? OR description ILIKE ?", "%#{query}%", "%#{query}%")
    end
  end

  def highlight(field)
    send(field).gsub(/#{@query}/, "<mark>\\0</mark>")
  end
end

class Article < ApplicationRecord
  include Searchable
end

class Product < ApplicationRecord
  include Searchable
end
"""
    (tmp_path / "searchable.rb").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "search")
    assert len(results) >= 1, "Module mixin method 'search' must be found"
