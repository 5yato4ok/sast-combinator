
"""
repo_info.py — Utility to derive DefectDojo Engagement fields from a local Git repository.

What it does:
  - Reads the local repo at --repo (or current directory).
  - Extracts: origin URL, current branch, HEAD commit hash.
  - Normalizes origin to a web URL that works in a browser (e.g. git@host:org/repo.git -> https://host/org/repo).
  - Supports common hosts: GitHub, GitLab, Bitbucket (Cloud/Server), Gitea/Codeberg, Azure DevOps; falls back generically.
  - Outputs JSON by default, or shell-exportable env variables with --env.

Usage examples:
  python repo_info.py --repo /path/to/repo
  python repo_info.py --repo . --env         # prints: REPO_URL=... BRANCH_TAG=... COMMIT_HASH=...
  python repo_info.py --repo . --prefer-commit  # prints JSON, but you can choose to use commit over branch externally
"""

from __future__ import annotations
import argparse
import os
import re
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RepoParams:
    repo_url: str
    branch_tag: Optional[str]
    commit_hash: str
    scm_type: str  # github|gitlab|bitbucket-cloud|bitbucket-server|gitea|codeberg|azure|generic


def run_git(repo: Path, args: list[str]) -> str:
    """Run a git command in the given repo and return stripped stdout."""
    cmd = ["git", "-C", str(repo)] + args
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    return out.strip()


def detect_scm_type(host: str) -> str:
    h = host.lower()
    if "github" in h:
        return "github"
    if "gitlab" in h:
        return "gitlab"
    if "bitbucket.org" in h:
        return "bitbucket-cloud"
    if "bitbucket" in h:
        return "bitbucket-server"
    if "codeberg" in h:
        return "codeberg"
    if "gitea" in h:
        return "gitea"
    if "dev.azure.com" in h or "visualstudio.com" in h:
        return "azure"
    return "generic"


def normalize_origin_to_web_url(origin: str) -> tuple[str, str]:
    """
    Convert a variety of Git remote URL formats to a browser-accessible web URL.
    Returns (web_url, scm_type).
    Examples:
      git@github.com:org/repo.git -> https://github.com/org/repo
      https://gitlab.example.com/group/repo.git -> https://gitlab.example.com/group/repo
      ssh://git@gitea.example.com/org/repo.git -> https://gitea.example.com/org/repo
      https://dev.azure.com/Org/Project/_git/Repo -> https://dev.azure.com/Org/Project/_git/Repo
    """
    origin = origin.strip()

    # Azure DevOps patterns
    m = re.match(r"^https?://(?P<host>[^/]+)/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)", origin)
    if m:
        host = m.group("host")
        scm = detect_scm_type(host)
        # Azure DevOps web URL is actually the same as clone URL for https
        web = f"https://{host}/{m.group('org')}/{m.group('project')}/_git/{m.group('repo')}"
        return web, scm
    m = re.match(r"^git@(?P<host>[^:]+):v3/(?P<org>[^/]+)/(?P<project>[^/]+)/(?P<repo>[^/]+)\.git$", origin)
    if m and "visualstudio.com" in m.group("host"):
        host = m.group("host")
        scm = detect_scm_type(host)
        web = f"https://{host}/{m.group('org')}/{m.group('project')}/_git/{m.group('repo')}"
        return web, scm

    # SSH scp-like: git@host:org/repo.git
    m = re.match(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$", origin)
    if m:
        host = m.group("host")
        path = m.group("path")
        path = re.sub(r"\.git$", "", path)
        scm = detect_scm_type(host)
        web = f"https://{host}/{path}".rstrip("/")
        return web, scm

    # SSH explicit: ssh://git@host/org/repo.git
    m = re.match(r"^ssh://(?P<user>[^@]+)@(?P<host>[^/]+)/(?P<path>.+)$", origin)
    if m:
        host = m.group("host")
        path = m.group("path")
        path = re.sub(r"\.git$", "", path)
        scm = detect_scm_type(host)
        web = f"https://{host}/{path}".rstrip("/")
        return web, scm

    # HTTPS: https://host/org/repo(.git)?
    m = re.match(r"^https?://(?P<host>[^/]+)/(?P<path>.+)$", origin)
    if m:
        host = m.group("host")
        path = re.sub(r"\.git$", "", m.group("path"))
        scm = detect_scm_type(host)
        web = f"https://{host}/{path}".rstrip("/")
        return web, scm

    # Fallback: return as-is (strip .git) and mark generic
    path = re.sub(r"\.git$", "", origin)
    return path, "generic"


def read_repo_params(repo_dir: str | Path) -> RepoParams:
    repo = Path(repo_dir).resolve()
    if not (repo / ".git").exists():
        # Allow worktrees/submodules; fallback to trusting git
        pass

    origin = run_git(repo, ["remote", "get-url", "origin"])
    branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit = run_git(repo, ["rev-parse", "HEAD"])
    web_url, scm = normalize_origin_to_web_url(origin)

    logger.info(f"Found git info. branch {branch}. commit {commit}. web url {web_url}. scm {scm}")

    # In detached HEAD state, branch can be 'HEAD'; treat as None
    if branch.upper() == "HEAD":
        branch = None

    return RepoParams(repo_url=web_url, branch_tag=branch, commit_hash=commit, scm_type=scm)


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive DefectDojo Engagement parameters from a local Git repo.")
    ap.add_argument("--repo", default=".", help="Path to local Git repository (default: current directory).")
    ap.add_argument("--env", action="store_true", help="Print shell-exportable variables instead of JSON.")
    args = ap.parse_args()

    info = read_repo_params(args.repo)
    if args.env:
        # Safe for eval in POSIX shells
        def esc(s: str) -> str:
            return "'" + s.replace("'", "'\"'\"'") + "'"
        print(f"REPO_URL={esc(info.repo_url)} BRANCH_TAG={esc(info.branch_tag or '')} COMMIT_HASH={esc(info.commit_hash)} SCM_TYPE={esc(info.scm_type)}")
    else:
        print({
            "repo_url": info.repo_url,
            "branch_tag": info.branch_tag,
            "commit_hash": info.commit_hash,
            "scm_type": info.scm_type,
        })

if __name__ == "__main__":
    main()
