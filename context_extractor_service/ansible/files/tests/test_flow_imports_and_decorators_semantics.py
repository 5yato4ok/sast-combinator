import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_decorators, find_imports


def test_find_imports_should_keep_real_tsx_import_lines():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(
            "import { useEffect, useState } from 'react';\n"
            "import { config } from '@/config';\n"
            "export default function OAuthDebugPage(){ return <div />; }\n",
        )

        imports = find_imports(root, "page.tsx")

    assert imports == [
        "import { useEffect, useState } from 'react';",
        "import { config } from '@/config';",
    ]


def test_find_imports_should_keep_real_python_import_lines():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "views.py").write_text(
            "import os\n"
            "from django.http import HttpResponse\n"
            "\n"
            "def login_view(request):\n"
            "    return HttpResponse('ok')\n",
        )

        imports = find_imports(root, "views.py")

    assert imports == [
        "import os",
        "from django.http import HttpResponse",
    ]

def test_find_decorators_should_keep_real_python_decorator_lines():
    source = """\
@permission_required('auth.view_user')
@audit_event('login')
def login_view(request):
    return True
"""

    decorators = find_decorators(source, Path("views.py"), 3)

    assert decorators == [
        "@permission_required('auth.view_user')",
        "@audit_event('login')",
    ]


def test_find_decorators_should_return_empty_for_undecorated_function():
    source = """\
def login_view(request):
    return True
"""

    decorators = find_decorators(source, Path("views.py"), 1)

    assert decorators == []
