import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_callers


def test_find_callers_should_not_return_exported_function_definition_as_caller():
    source = """\
import { useState } from 'react';

export default function OAuthDebugPage() {
  const [code, setCode] = useState(null);
  return code;
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(source)

        result = find_callers(root, "page.tsx", "OAuthDebugPage")

    assert result == []
