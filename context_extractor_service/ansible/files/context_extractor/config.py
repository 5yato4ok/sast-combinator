"""Centralized language-specific configuration (no heavy imports here)."""

from __future__ import annotations

from typing import TypedDict


class LangNodeset(TypedDict):
    """Type-safe definition for per-language AST node type sets."""

    function: set[str]
    block: set[str]
    key: set[str]
    ident: set[str]
    runtime_ident: set[str]
    member_like: set[str]
    assign: set[str]
    declaration: set[str]
    loop: set[str]
    call: set[str]
    control: set[str]
    closing_is_brace: bool
    line_comment_prefix: str


# Directories to always skip when walking a project tree — shared across modules.
SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg", ".idea", ".vscode",
    "node_modules", "__pycache__", ".tox", ".mypy_cache",
    "vendor", "build", "dist", ".next",
    "target", "bin", "obj", ".gradle",
})

# Node type sets per language key used by Tree-sitter grammars.
LANG_NODESETS: dict[str, LangNodeset] = {
    "cpp": {
        "function": {"function_definition", "function_declaration", "lambda_expression"},
        "block": {"compound_statement", "lambda_expression", "function_definition"},
        "key": {
            # statements we consider "key" for matching/expansion
            "assignment_expression", "compound_assignment_expression",
            "declaration", "call_expression",
            "if_statement", "return_statement",
            "for_statement", "for_range_loop",
        },
        "ident": {"identifier", "field_identifier", "scoped_identifier"},
        "runtime_ident": {"identifier", "field_identifier", "scoped_identifier"},
        "member_like": {"field_expression", "scoped_identifier"},
        "assign": {"assignment_expression", "compound_assignment_expression"},
        "declaration": {"declaration", "init_declarator"},
        "loop": {"for_statement", "for_range_loop"},
        "call": {"call_expression"},
        # control parents we may want to promote into output
        "control": {
            "if_statement", "for_statement", "for_range_loop",
            "while_statement", "do_statement", "switch_statement",
        },
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "java": {
        "function": {"method_declaration", "constructor_declaration", "lambda_expression"},
        "block": {"block", "lambda_expression"},
        "key": {
            "assignment_expression", "local_variable_declaration", "method_invocation",
            "if_statement", "return_statement", "for_statement", "enhanced_for_statement",
        },
        "ident": {"identifier"},
        "runtime_ident": {"identifier"},
        "member_like": {"field_access", "method_invocation"},
        "loop": {"for_statement", "enhanced_for_statement"},
        "assign": {"assignment_expression"},
        "declaration": {"local_variable_declaration"},
        "call": {"method_invocation"},
        "control": {
            "if_statement", "for_statement", "enhanced_for_statement",
            "while_statement", "switch_expression", "switch_statement",
        },
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "javascript": {
        "function": {"function_declaration", "function", "method_definition", "arrow_function"},
        "block": {"statement_block", "function", "method_definition"},
        "key": {
            "assignment_expression", "augmented_assignment_expression",
            "variable_declaration", "lexical_declaration", "call_expression",
            "if_statement", "return_statement", "for_statement",
            "for_in_statement", "for_of_statement",
        },
        "ident": {"identifier", "shorthand_property_identifier", "property_identifier"},
        "runtime_ident": {"identifier", "shorthand_property_identifier", "property_identifier"},
        "member_like": {"member_expression"},
        "assign": {"assignment_expression", "augmented_assignment_expression"},
        "declaration": {"variable_declaration", "lexical_declaration"},
        "loop": {"for_statement", "for_in_statement", "for_of_statement"},
        "call": {"call_expression"},
        "control": {
            "if_statement", "for_statement", "for_in_statement",
            "for_of_statement", "while_statement", "switch_statement",
        },
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "python": {
        "function": {"function_definition", "lambda"},
        "block": {"block", "function_definition"},
        "key": {
            "assignment", "augmented_assignment",
            "expression_statement", "call",
            "if_statement", "return_statement", "for_statement",
            "with_statement",
        },
        "ident": {"identifier"},
        "runtime_ident": {"identifier"},
        "member_like": {"attribute"},
        "assign": {"assignment", "augmented_assignment"},
        "declaration": set(),
        "call": {"call"},
        "loop": {"for_statement"},
        "control": {"if_statement", "for_statement", "while_statement"},
        "closing_is_brace": False,
        "line_comment_prefix": "#",
    },

    "csharp": {
        "function": {
            "method_declaration", "constructor_declaration", "local_function_statement",
            "lambda_expression", "anonymous_method_expression", "property_declaration",
            "indexer_declaration", "operator_declaration", "delegate_declaration",
        },
        "block": {
            "block", "method_declaration", "constructor_declaration", "local_function_statement",
            "lambda_expression", "anonymous_method_expression", "property_declaration",
            "indexer_declaration", "operator_declaration",
        },
        "key": {"assignment_expression", "declaration_expression", "invocation_expression",
                "if_statement", "return_statement", "for_statement", "foreach_statement", "while_statement"},
        "ident": {"identifier"},
        "runtime_ident": {"identifier"},
        "member_like": {
            "member_access_expression", "qualified_name",
            "member_binding_expression", "element_access_expression",
        },
        "assign": {"assignment_expression", "compound_assignment_expression"},
        "declaration": {"local_declaration_statement", "variable_declaration", "declaration_expression"},
        "call": {"invocation_expression", "object_creation_expression"},
        "loop": {"for_statement", "foreach_statement", "while_statement"},
        "control": {"if_statement", "for_statement", "foreach_statement", "while_statement"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "typescript": {
        "function": {"function_declaration", "method_definition", "arrow_function", "function_signature"},
        "block": {"statement_block", "function_declaration", "class_body"},
        "key": {"assignment_expression", "lexical_declaration", "call_expression",
                "if_statement", "return_statement", "for_statement", "while_statement",
                "for_in_statement", "for_of_statement", "public_field_definition"},
        "ident": {"identifier", "shorthand_property_identifier"},
        "runtime_ident": {"identifier", "shorthand_property_identifier"},
        "member_like": {"member_expression", "subscript_expression"},
        "assign": {"assignment_expression", "augmented_assignment_expression"},
        "declaration": {"lexical_declaration", "variable_declaration", "public_field_definition"},
        "call": {"call_expression"},
        "loop": {"for_statement", "while_statement", "for_in_statement", "for_of_statement"},
        "control": {"if_statement", "for_statement", "while_statement", "for_in_statement", "for_of_statement"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "go": {
        "function": {"function_declaration", "method_declaration"},
        "block": {"block", "function_declaration", "method_declaration"},
        "key": {"short_var_declaration", "assignment_statement", "call_expression",
                "if_statement", "return_statement", "for_statement"},
        "ident": {"identifier"},
        "runtime_ident": {"identifier"},
        "member_like": {"selector_expression"},
        "assign": {"short_var_declaration", "assignment_statement"},
        "declaration": {"short_var_declaration"},
        "call": {"call_expression"},
        "loop": {"for_statement"},
        "control": {"if_statement", "for_statement"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "ruby": {
        "function": {"method", "singleton_method"},
        "block": {"block", "method"},
        "key": {"assignment", "call", "if", "return"},
        "ident": {"identifier", "constant"},
        "runtime_ident": {"identifier", "constant"},
        "member_like": {"call"},
        "assign": {"assignment", "operator_assignment"},
        "declaration": set(),
        "call": {"call"},
        "loop": {"for"},
        "control": {"if", "elsif", "unless"},
        "closing_is_brace": False,
        "line_comment_prefix": "#",
    },
    "kotlin": {
        "function": {"function_declaration"},
        "block": {"block", "function_declaration"},
        "key": {"assignment", "call_expression", "if_expression", "return_expression", "for_statement",
                "while_statement"},
        "ident": {"simple_identifier"},
        "runtime_ident": {"simple_identifier"},
        "member_like": {"navigation_expression", "member_access_operator"},
        "assign": {"assignment"},
        "declaration": {"property_declaration", "local_variable_declaration"},
        "call": {"call_expression"},
        "loop": {"for_statement", "while_statement"},
        "control": {"if_expression", "when_expression", "for_statement", "while_statement"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    # PHP language support
    "php": {
        # Node types considered as functions: global functions, class methods, anonymous functions and arrows
        "function": {
            "function_definition", "method_declaration",
            "anonymous_function_creation_expression", "arrow_function"
        },
        # Blocks for PHP include compound statements and function-like bodies
        "block": {
            "compound_statement", "function_definition",
            "method_declaration", "anonymous_function_creation_expression"
        },
        # Key statements drive backward expansion during compression.
        # Include assignments, generic expression statements, calls, control flow and loops.
        "key": {
            "assignment_expression", "expression_statement", "function_call_expression",
            "if_statement", "return_statement",
            "for_statement", "while_statement", "foreach_statement"
        },
        # Identifier nodes. PHP exposes variable names via 'variable_name' and generic 'name'.
        "ident": {"name", "variable_name"},
        "runtime_ident": {"name", "variable_name"},
        # Member-like expressions such as property/method accesses and static calls
        "member_like": {"member_access_expression", "scoped_call_expression"},
        # Assignment expression node
        "assign": {"assignment_expression"},
        # PHP doesn't have standalone variable declarations; leave empty
        "declaration": set(),
        # Call expressions: function, method and static calls
        "call": {"function_call_expression", "method_call_expression", "scoped_call_expression"},
        # Loop statements recognised when collecting write identifiers
        "loop": {"for_statement", "while_statement", "foreach_statement"},
        # Control statements to promote into output when relevant
        "control": {"if_statement", "for_statement", "while_statement", "foreach_statement"},
        # PHP functions use braces for their bodies
        "closing_is_brace": True,
        # Use C-style line comments as default for compress error messages
        "line_comment_prefix": "//",
    },
    "json": {
        "function": set(),
        "block": {"object", "array"},
        "key": {"pair", "object", "array"},
        "ident": set(),
        "runtime_ident": set(),
        "member_like": set(),
        "assign": set(),
        "declaration": set(),
        "loop": set(),
        "call": set(),
        "control": set(),
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "bash": {
        "function": {"function_definition"},
        "block": {"compound_statement", "function_definition"},
        "key": {"variable_assignment", "command", "redirected_statement", "if_statement"},
        "ident": {"variable_name", "command_name", "word"},
        "runtime_ident": {"variable_name"},
        "member_like": set(),
        "assign": {"variable_assignment"},
        "declaration": set(),
        "loop": {"for_statement", "while_statement"},
        "call": {"command"},
        "control": {"if_statement", "for_statement", "while_statement"},
        "closing_is_brace": False,
        "line_comment_prefix": "#",
    },
    "qml": {
        "function": {"function_declaration"},
        "block": {"program", "ui_object_initializer", "statement_block", "function_declaration"},
        "key": {"ui_property", "ui_binding", "expression_statement", "call_expression", "function_declaration"},
        "ident": {"identifier", "property_identifier"},
        "runtime_ident": {"identifier", "property_identifier"},
        "member_like": {"member_expression"},
        "assign": set(),
        "declaration": {"ui_property", "ui_binding"},
        "callable_binding": {"ui_binding"},
        "loop": set(),
        "call": {"call_expression"},
        "control": set(),
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
}

# Per-language comment styles (for full and inline comments)
COMMENT_STYLE = {
    "cpp":         {"line": ["//"], "block": [("/*", "*/")]},
    "java":        {"line": ["//"], "block": [("/*", "*/")]},
    "javascript":  {"line": ["//"], "block": [("/*", "*/")]},
    "python":      {"line": ["#"],  "block": []},
    "csharp":      {"line": ["//"], "block": [("/*", "*/")]},
    "typescript":  {"line": ["//"], "block": [("/*", "*/")]},
    "go":          {"line": ["//"], "block": [("/*", "*/")]},
    "ruby":        {"line": ["#"], "block": []},
    "kotlin":      {"line": ["//"], "block": [("/*", "*/")]},
    "php":         {"line": ["//", "#"], "block": [("/*", "*/")]},
    "json":        {"line": [], "block": []},
    "bash":        {"line": ["#"], "block": []},
}
