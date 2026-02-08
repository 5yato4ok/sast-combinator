from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "Dockerfile.django-debian").exists():
            return parent
    raise AssertionError("Could not locate Dockerfile.django-debian from test path.")


def test_dockerfile_buildx_version_is_pinned():
    repo_root = _find_repo_root(Path(__file__).resolve())
    debian_dockerfile = repo_root / "Dockerfile.django-debian"
    alpine_dockerfile = repo_root / "Dockerfile.django-alpine"

    debian_content = debian_dockerfile.read_text(encoding="utf-8")
    alpine_content = alpine_dockerfile.read_text(encoding="utf-8")

    for content in (debian_content, alpine_content):
        assert "ARG DOCKER_BUILDX_VERSION=" in content
        assert "buildx-v${DOCKER_BUILDX_VERSION}.linux-${buildx_arch}" in content

    assert "docker-buildx-plugin" not in debian_content
    assert "docker-cli-buildx" not in alpine_content
