# ruff: noqa: INP001, S101

from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "input_projects" / "default_imported_project_no_built.sh"


def read_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_node_install_uses_lockfile_priority_and_fallbacks():
    content = read_script()

    pnpm_idx = content.index('if [ -f "pnpm-lock.yaml" ]; then')
    yarn_idx = content.index('elif [ -f "yarn.lock" ]; then')
    npm_lock_idx = content.index('elif [ -f "package-lock.json" ]; then')
    npm_idx = content.index('elif [ -f "package.json" ]; then')

    assert pnpm_idx < yarn_idx < npm_lock_idx < npm_idx
    assert 'install_with_log "pnpm install --frozen-lockfile" pnpm install --frozen-lockfile' in content
    assert 'install_with_log "npm install (fallback)" npm install' in content
    assert 'install_with_log "npm ci" npm ci' in content


def test_node_install_uses_corepack_and_no_global_installs():
    content = read_script()

    assert 'install_with_log "corepack enable" corepack enable' in content
    assert 'install_with_log "corepack prepare pnpm --activate" corepack prepare pnpm --activate' in content
    assert 'install_with_log "corepack prepare yarn --activate" corepack prepare yarn --activate' in content
    assert "npm install -g yarn" not in content
    assert "npm install -g pnpm" not in content


def test_node_install_handles_failures_without_immediate_exit():
    content = read_script()

    assert "install_with_log()" in content
    assert "install_node_deps()" in content
    assert "set +e" in content
    assert 'echo "[NODE][ERROR] All dependency installation methods failed"' in content
    assert 'if [ "$NEED_NODE" -eq 1 ]; then' in content
    assert "install_node_deps" in content


def test_node_install_skips_package_lock_without_package_json():
    content = read_script()

    assert 'elif [ -f "package-lock.json" ] && [ -f "package.json" ]; then' in content
    assert 'elif [ -f "package-lock.json" ]; then' in content
    assert 'package-lock.json found without package.json' in content
    assert 'install_with_log "npm ci" npm ci' in content


def test_node_install_prefers_npm_ci_when_package_lock_and_package_json_exist():
    content = read_script()

    assert 'elif [ -f "package-lock.json" ] && [ -f "package.json" ]; then' in content
    assert 'install_with_log "npm ci" npm ci' in content
    assert 'install_with_log "npm install (fallback)" npm install' in content


def test_node_install_handles_no_valid_node_manifests_without_failure():
    content = read_script()

    assert 'if [ -f "package.json" ] || [ -f "yarn.lock" ] || [ -f "pnpm-lock.yaml" ] || [ -f "package-lock.json" ]; then' in content
    assert 'if [ "$NEED_NODE" -eq 1 ]; then' in content


def test_node_install_does_not_use_recursive_manifest_search():
    content = read_script()

    assert 'find "$DEV_DIR" -type f' not in content


def test_node_install_failure_does_not_hard_fail_script():
    content = read_script()

    assert 'if [ "$node_install_rc" -ne 0 ]; then' in content
    assert "continuing without Node deps" in content
    assert 'exit 1' not in content.split('if [ "$node_install_rc" -ne 0 ]; then', 1)[1].split("fi", 1)[0]
