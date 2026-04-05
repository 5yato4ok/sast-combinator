"""
Edge case tests for modern C# language features.

Covers:
- Record types: positional record, record with methods, record struct
- Pattern matching: capture, property, and recursive patterns in switch expressions
- Top-level statements (C# 9+): no class / Main wrapper
- Nullable reference types: ?., ??, !, string? parameters
- Required properties (C# 11): required keyword on property
"""
import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


# ---------------------------------------------------------------------------
# 1. Record types
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_method_defined_inside_record():
    """extract_function must return the full body of a method inside a record declaration."""
    source = """\
public record Person(string Name, int Age)
{
    public string Greet() =>
        $"Hello, {Name}! You are {Age} years old.";
}
"""
    result = extract_function_from_source(source, "Person.cs", 3, 200)
    assert result is not None and "text" in result
    assert "Greet" in result["text"]


def test_find_definition_should_locate_positional_record_type(tmp_path):
    """find_definition must find a positional record type by its name."""
    src = """\
public record Point(double X, double Y);

public record Circle(Point Center, double Radius)
{
    public double Area() => Math.PI * Radius * Radius;
}
"""
    (tmp_path / "shapes.cs").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "Point")
    assert len(results) >= 1, "Positional record 'Point' definition must be found"
    assert any(r.get("kind") == "class" for r in results)


def test_find_identifiers_should_capture_arguments_in_record_constructor_call(monkeypatch):
    """find_identifiers on 'new Person(name, age)' must capture name and age as reads."""
    source = """\
public class Factory
{
    public Person CreatePerson(string name, int age)
    {
        return new Person(name, age);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Factory.cs"))
    result = mcp_server.find_identifiers("pipe", "Factory.cs", 5)
    assert "name" in result["reads"], "name must be a read in record constructor call"
    assert "age" in result["reads"], "age must be a read in record constructor call"


# ---------------------------------------------------------------------------
# 2. Pattern matching in switch expressions
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_type_pattern_binding_as_write(monkeypatch):
    """find_identifiers on 'Circle c when c.Radius > 1' must put 'c' in writes."""
    source = """\
public static string Describe(Shape shape)
{
    return shape switch
    {
        Circle c when c.Radius > 1 => $"Big circle r={c.Radius}",
        Circle c => "Small circle",
        _ => "Other shape"
    };
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Shapes.cs"))
    result = mcp_server.find_identifiers("pipe", "Shapes.cs", 5)
    assert "c" in result["writes"], "Pattern capture variable 'c' must be a write"


def test_find_identifiers_should_capture_var_binding_in_property_pattern(monkeypatch):
    """find_identifiers on '{ Name: { Length: var len } }' must put 'len' in writes."""
    source = """\
public static int GetNameLength(Person p)
{
    return p switch
    {
        { Name: { Length: var len } } => len,
        _ => 0
    };
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Pattern.cs"))
    result = mcp_server.find_identifiers("pipe", "Pattern.cs", 5)
    assert "len" in result["writes"], "var-binding 'len' in property pattern must be a write"


def test_trace_identifier_backward_should_reach_switch_expression_assignment(monkeypatch):
    """trace_identifier_backward must trace 'area' back to the switch expression that sets it."""
    source = """\
public static double ComputeArea(Shape s)
{
    var area = s switch
    {
        Circle c => Math.PI * c.Radius * c.Radius,
        Rectangle r => r.Width * r.Height,
        _ => 0.0
    };
    return area;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Area.cs"))
    chain = mcp_server.trace_identifier_backward("pipe", "Area.cs", 9, "area")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in range(3, 9) for entry in chain), \
        "Trace must reach the switch expression assigning 'area'"


# ---------------------------------------------------------------------------
# 3. Top-level statements (C# 9+)
# ---------------------------------------------------------------------------

def test_extract_function_should_extract_local_function_in_top_level_statements():
    """extract_function must handle a local function defined directly in top-level code."""
    source = """\
using System;

Console.WriteLine(Greet("World"));

string Greet(string name) =>
    $"Hello, {name}!";
"""
    result = extract_function_from_source(source, "Program.cs", 5, 200)
    assert result is not None and "text" in result
    assert "Greet" in result["text"]


def test_find_imports_should_extract_using_directives_from_top_level_file(monkeypatch):
    """find_imports must return using-directives from a file with top-level statements."""
    source = """\
using System;
using System.Collections.Generic;
using System.Linq;

var numbers = new List<int> { 1, 2, 3, 4, 5 };
var evens = numbers.Where(n => n % 2 == 0).ToList();
Console.WriteLine(evens.Count);
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "script.cs"))
    imports = mcp_server.find_imports("pipe", "script.cs")
    assert any("System" in imp for imp in imports), "using System must be detected"
    assert any("Linq" in imp for imp in imports), "using System.Linq must be detected"


def test_find_callers_should_find_call_to_local_function_in_top_level_code(tmp_path):
    """find_callers must locate invocations of a local function inside top-level statements."""
    src = """\
using System;

var result = Compute(42);
Console.WriteLine(result);

int Compute(int x) => x * x;
"""
    (tmp_path / "toplevel.cs").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "toplevel.cs", "Compute")
    assert len(results) >= 1, "Call to 'Compute' in top-level code must be found"
    assert any(r["line"] == 3 for r in results)


# ---------------------------------------------------------------------------
# 4. Nullable reference types
# ---------------------------------------------------------------------------

def test_find_identifiers_should_capture_null_conditional_receiver(monkeypatch):
    """find_identifiers on 'processor?.Process(data)' must capture 'processor' as a read."""
    source = """\
public class Service
{
    public void Execute(IProcessor? processor, string data)
    {
        var result = processor?.Process(data);
        Log(result);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Service.cs"))
    result = mcp_server.find_identifiers("pipe", "Service.cs", 5)
    assert "processor" in result["reads"], "Null-conditional receiver must be a read"
    assert "result" in result["writes"], "LHS 'result' must be a write"


def test_find_identifiers_should_capture_both_operands_of_null_coalescing(monkeypatch):
    """find_identifiers on 'raw ?? GetDefault(key)' must capture 'raw' and 'GetDefault'."""
    source = """\
public class Config
{
    public string GetSetting(string key)
    {
        var raw = _store.Get(key);
        return raw ?? GetDefault(key);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Config.cs"))
    result = mcp_server.find_identifiers("pipe", "Config.cs", 6)
    assert "raw" in result["reads"], "Left operand of '??' must be a read"
    assert "GetDefault" in result["reads"], "Right operand function call must be a read"


def test_extract_function_should_preserve_nullable_annotations_in_signature():
    """extract_function must return the function signature with all nullable type annotations."""
    source = """\
public class Parser
{
    public string? TryParse(string? input)
    {
        if (input is null) return null;
        return input.Trim();
    }
}
"""
    result = extract_function_from_source(source, "Parser.cs", 3, 200)
    assert result is not None and "text" in result
    assert "?" in result["text"], "Nullable type annotations must be preserved"


# ---------------------------------------------------------------------------
# 5. Required properties (C# 11)
# ---------------------------------------------------------------------------

def test_find_definition_should_find_required_property_declaration(tmp_path):
    """find_definition must locate a required property on a class by its name."""
    src = """\
public class UserProfile
{
    public required string Username { get; set; }
    public required string Email { get; set; }
    public int? Age { get; set; }
}
"""
    (tmp_path / "UserProfile.cs").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "Username")
    assert len(results) >= 1, "required property 'Username' must be found by find_definition"


def test_find_identifiers_should_capture_reads_in_required_property_object_initializer(monkeypatch):
    """find_identifiers on object init with required props must capture the RHS values."""
    source = """\
public class Factory
{
    public UserProfile Create(string user, string email)
    {
        return new UserProfile { Username = user, Email = email };
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Factory.cs"))
    result = mcp_server.find_identifiers("pipe", "Factory.cs", 5)
    assert "user" in result["reads"] or "email" in result["reads"], \
        "RHS values in required property init must be captured as reads"


def test_extract_function_should_extract_method_that_accesses_required_property():
    """extract_function must extract a method body that reads required properties."""
    source = """\
public class UserService
{
    public bool IsValid(UserProfile profile)
    {
        return profile.Username.Length > 0
            && profile.Email.Contains("@");
    }
}
"""
    result = extract_function_from_source(source, "UserService.cs", 4, 200)
    assert result is not None and "text" in result
    assert "IsValid" in result["text"]
    assert "Username" in result["text"] or "Email" in result["text"]
