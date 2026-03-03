# ruff: noqa: INP001, S101

import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "input_projects" / "default_imported_project_no_built.sh"


def read_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _git(repo_dir: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=repo_dir,
        check=check,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _configure_git_identity(repo_dir: Path) -> None:
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test User")


def _commit_file(repo_dir: Path, file_name: str, content: str, message: str) -> str:
    (repo_dir / file_name).write_text(content, encoding="utf-8")
    _git(repo_dir, "add", file_name)
    _git(repo_dir, "commit", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD")


def _run_script(
    project_root: Path,
    repo_url: str,
    project_name: str,
    project_version: str,
    project_version_type: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "REPO_URL": repo_url,
            "PROJECT_NAME": project_name,
            "PROJECT_VERSION": project_version,
            "FORCE_REBUILD": "0",
        }
    )
    if project_version_type is not None:
        env["PROJECT_VERSION_TYPE"] = project_version_type
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT_PATH), str(project_root)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


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


def test_project_version_branch_prefers_origin_when_local_branch_diverged(tmp_path):
    origin = tmp_path / "origin.git"
    seed_repo = tmp_path / "seed"
    builder_root = tmp_path / "builder-root"
    project_name = "demo"
    dev_dir = builder_root / project_name

    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed_repo))
    _configure_git_identity(seed_repo)
    _commit_file(seed_repo, "app.txt", "base\n", "base")
    _git(seed_repo, "branch", "-M", "main")
    _git(seed_repo, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(seed_repo, "checkout", "-b", "feature")
    _commit_file(seed_repo, "app.txt", "feature-v1\n", "feature v1")
    _git(seed_repo, "push", "-u", "origin", "feature")

    _git(tmp_path, "clone", str(origin), str(dev_dir))
    _configure_git_identity(dev_dir)
    _git(dev_dir, "checkout", "-b", "feature", "origin/feature")
    local_only_commit = _commit_file(dev_dir, "app.txt", "local-only\n", "local only")

    updater_repo = tmp_path / "updater"
    _git(tmp_path, "clone", str(origin), str(updater_repo))
    _configure_git_identity(updater_repo)
    _git(updater_repo, "checkout", "feature")
    origin_new_commit = _commit_file(updater_repo, "app.txt", "origin-new\n", "origin new")
    _git(updater_repo, "push", "origin", "feature")

    result = _run_script(builder_root, str(origin), project_name, "feature", project_version_type="GIT_BRANCH")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert _git(dev_dir, "rev-parse", "HEAD") == origin_new_commit
    assert _git(dev_dir, "rev-parse", "HEAD") != local_only_commit


def test_project_version_explicit_commit_sha_uses_exact_sha(tmp_path):
    origin = tmp_path / "origin.git"
    seed_repo = tmp_path / "seed"
    builder_root = tmp_path / "builder-root"
    project_name = "demo"

    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed_repo))
    _configure_git_identity(seed_repo)
    target_commit = _commit_file(seed_repo, "app.txt", "commit-1\n", "commit 1")
    _commit_file(seed_repo, "app.txt", "commit-2\n", "commit 2")
    _git(seed_repo, "branch", "-M", "main")
    _git(seed_repo, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

    result = _run_script(builder_root, str(origin), project_name, target_commit, project_version_type="GIT_HASH")
    dev_dir = builder_root / project_name

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert _git(dev_dir, "rev-parse", "HEAD") == target_commit


def test_project_version_invalid_fails_with_error(tmp_path):
    origin = tmp_path / "origin.git"
    seed_repo = tmp_path / "seed"
    builder_root = tmp_path / "builder-root"

    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed_repo))
    _configure_git_identity(seed_repo)
    _commit_file(seed_repo, "app.txt", "base\n", "base")
    _git(seed_repo, "branch", "-M", "main")
    _git(seed_repo, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

    result = _run_script(builder_root, str(origin), "demo", "no-such-version")

    assert result.returncode != 0
    assert "Can't resolve PROJECT_VERSION='no-such-version'" in result.stderr


def test_project_version_invalid_type_fails_with_error(tmp_path):
    origin = tmp_path / "origin.git"
    seed_repo = tmp_path / "seed"
    builder_root = tmp_path / "builder-root"

    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed_repo))
    _configure_git_identity(seed_repo)
    _commit_file(seed_repo, "app.txt", "base\n", "base")
    _git(seed_repo, "branch", "-M", "main")
    _git(seed_repo, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

    result = _run_script(builder_root, str(origin), "demo", "main", project_version_type="unknown")

    assert result.returncode != 0
    assert "Unsupported PROJECT_VERSION_TYPE='unknown'" in result.stderr


def test_project_version_git_hash_local_only_commit_fails(tmp_path):
    origin = tmp_path / "origin.git"
    seed_repo = tmp_path / "seed"
    builder_root = tmp_path / "builder-root"
    project_name = "demo"
    dev_dir = builder_root / project_name

    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed_repo))
    _configure_git_identity(seed_repo)
    _commit_file(seed_repo, "app.txt", "base\n", "base")
    _git(seed_repo, "branch", "-M", "main")
    _git(seed_repo, "push", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

    _git(tmp_path, "clone", str(origin), str(dev_dir))
    _configure_git_identity(dev_dir)
    local_only_commit = _commit_file(dev_dir, "app.txt", "local-only\n", "local only")

    result = _run_script(
        builder_root,
        str(origin),
        project_name,
        local_only_commit,
        project_version_type="GIT_HASH",
    )

    assert result.returncode != 0
    assert f"Can't resolve GIT_HASH PROJECT_VERSION='{local_only_commit}' on origin." in result.stderr
