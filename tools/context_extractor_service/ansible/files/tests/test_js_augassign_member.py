import pytest
from context_extractor.compress import compress_function_from_source

@pytest.mark.js
def test_js_alias_chain_and_augassign_and_member_cond():
  SRC = r"""
// header
function foo(obj, b) {
  // alias chain
  let x = b.c; // alias-1
  let y = x; // alias-2

  let a = 0;
  a += b.c.d; // aug-assign

  if (obj.foo().bar > 1) { // complex member_expression
    return a; // target
  }
  return 0;
}
"""
  line = next(i for i,l in enumerate(SRC.splitlines(),1) if "return a; // target" in l)
  out = compress_function_from_source(SRC, "file.js", line)
  text = out["text"]
  assert "let x = b.c" in text
  assert "let y = x" in text
  assert "a += b.c.d" in text
  assert "if (obj.foo().bar > 1)" in text
  assert out["meta"]["language"] == "javascript"
