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
