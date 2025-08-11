# Centralized language-specific configuration (no heavy imports here).

# Node type sets per language key used by Tree-sitter grammars.
LANG_NODESETS = {
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
        },
        "ident": {"identifier"},
        "member_like": {"attribute"},
        "assign": {"assignment", "augmented_assignment"},
        "declaration": set(),
        "call": {"call"},
        "loop": {"for_statement"},
        "control": {"if_statement", "for_statement", "while_statement"},
        "closing_is_brace": False,
        "line_comment_prefix": "#",
    },
}

# Per-language comment styles (for full and inline comments)
COMMENT_STYLE = {
    "cpp":         {"line": ["//"], "block": [("/*", "*/")]},
    "java":        {"line": ["//"], "block": [("/*", "*/")]},
    "javascript":  {"line": ["//"], "block": [("/*", "*/")]},
    "python":      {"line": ["#"],  "block": []},
}
