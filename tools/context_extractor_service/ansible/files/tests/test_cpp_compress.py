import pytest
from context_extractor.compress import compress_function_from_source

@pytest.mark.cpp
def test_cpp_preserves_comments_and_controls():
    CPP_SRC = r"""
// File header

// lead comment (outside function)
int add(int a, int b)
{
    // entry
    int s = a + b; // inline-keep-me

    int dummy = 0; // inline-omit-me

    for (int i = 0; i < b; ++i) {
        s = s + i;
    }

    /* block comment header */
    if (s > 100) { /* guard */
        s -= 42;
    }
    // tail
    return s; // tail-inline
}
"""
    line = next(i for i,l in enumerate(CPP_SRC.splitlines(),1) if "return s" in l)
    out = compress_function_from_source(CPP_SRC, "example.cpp", line)
    text = out["text"]
    assert "// entry" in text
    assert "// tail" in text
    assert "/* block comment header */" in text
    assert "for (int i = 0; i < b; ++i)" in text
    assert "if (s > 100)" in text
    assert "// ... omitted ..." in text
    assert "… // inline-omit-me" in text
    assert "int s = a + b; // inline-keep-me" in text
    assert out["meta"]["language"] == "cpp"

@pytest.mark.cpp
def test_cpp_range_based_for_auto_ref_and_field_expr():
    SRC = r"""
#include <vector>
namespace ns { struct Obj { static Obj& get(); int field; }; }
int sum(const std::vector<int>& v) {
    // head
    int s = 0;
    for (auto& x : v) { // rb-for
        s += x; // aug-like
    }
    if (ns::Obj::get().field > 0) {
        return s; // target
    }
    return 0;
}
"""
    line = next(i for i,l in enumerate(SRC.splitlines(),1) if "return s; // target" in l)
    out = compress_function_from_source(SRC, "rb.cpp", line)
    text = out["text"]
    assert "for (auto& x : v)" in text or "for (auto & x : v)" in text or "for (auto&  x : v)" in text
    assert "if (ns::Obj::get().field > 0)" in text
    assert "// head" in text
