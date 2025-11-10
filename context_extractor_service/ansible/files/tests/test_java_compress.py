import pytest
from context_extractor.compress import compress_function_from_source
pytest.skip("Ignore compress tests", allow_module_level=True)

@pytest.mark.java
def test_java_enhanced_for_and_if():
    SRC = r"""
// header
class A {
    // comment-outer
    public int sum(java.util.List<Integer> xs) {
        // inside
        int s = 0;
        for (int x : xs) { // enhanced for
            s += x;
        }
        if (s > 10) {
            return s; // target
        }
        return 0;
    }
}
"""
    line = next(i for i,l in enumerate(SRC.splitlines(),1) if "return s; // target" in l)
    out = compress_function_from_source(SRC, "X.java", line)
    text = out["text"]
    assert "// inside" in text
    assert "for (int x : xs)" in text
    assert "if (s > 10)" in text
    assert out["meta"]["language"] == "java"
