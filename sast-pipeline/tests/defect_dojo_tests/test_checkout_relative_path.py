import pytest

from pipeline.defect_dojo.repo_info import checkout_relative_path


@pytest.mark.parametrize(
    ("file_path", "trim_path", "expected"),
    [
        ("/workspace/shop/src/app.py", "/workspace/shop", "src/app.py"),
        ("/workspace/shop/src/app.py", "/workspace/shop/", "src/app.py"),
        ("/workspace/shop/vendor/workspace/shop/lib.py", "/workspace/shop", "vendor/workspace/shop/lib.py"),
        ("/workspace/shopfront/app.py", "/workspace/shop", "/workspace/shopfront/app.py"),
        ("src/app.py", "/workspace/shop", "src/app.py"),
        ("/workspace/shop/src/app.py", "", "/workspace/shop/src/app.py"),
    ],
)
def test_only_the_leading_checkout_root_is_removed(file_path, trim_path, expected):
    assert checkout_relative_path(file_path, trim_path) == expected


@pytest.mark.parametrize(
    ("file_path", "trim_path", "expected"),
    [
        # ESLint's SARIF formatter reports absolute file URIs.
        ("file:///workspace/shop/src/app/page.tsx", "/workspace/shop", "src/app/page.tsx"),
        ("file:///workspace/shop/src/my%20module/%5Bslug%5D/page.tsx", "/workspace/shop", "src/my module/[slug]/page.tsx"),
        ("file://localhost/workspace/shop/src/app.js", "/workspace/shop", "src/app.js"),
        ("file:///workspace/shopfront/app.js", "/workspace/shop", "/workspace/shopfront/app.js"),
        ("file:///workspace/shop/src/app.js", "", "/workspace/shop/src/app.js"),
    ],
)
def test_a_file_uri_is_made_relative_to_the_checkout_root(file_path, trim_path, expected):
    assert checkout_relative_path(file_path, trim_path) == expected
