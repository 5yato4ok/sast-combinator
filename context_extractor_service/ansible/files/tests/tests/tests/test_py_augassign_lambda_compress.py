import pytest
from context_extractor.compress import compress_function_from_source
pytest.skip("Ignore compress tests", allow_module_level=True)
@pytest.mark.py
def test_python_lambda_augassign_and_attr_cond():
    SRC = """

# module header

def outer(n, obj):
    # comment inside def
    val = 0
    val += n  # aug
    f = lambda x: x + val  # lambda target
    # intermezzo
    if obj.attr.value > 0:
        return f(n)  # target
    return 0
"""
    line = next(i for i,l in enumerate(SRC.splitlines(),1) if "return f(n)" in l)
    out = compress_function_from_source(SRC, "file.py", line)
    text = out["text"]
    assert "# comment inside def" in text
    assert "val += n" in text
    assert "lambda x:" in text
    assert "if obj.attr.value > 0" in text
    assert out["meta"]["language"] == "python"
