"""CodeQL analyses Go by building it, in a container that has neither credentials nor VPN.

The build therefore has to come out of a module cache the builder left on the shared volume.
Three files have to agree on that for a Go pipeline to produce anything at all, and each has
been "simplified" back to a broken state before: the builder writing the cache somewhere the
analyzer cannot see, the image shipping a Go too old for the project's go.mod, or the analyzer
reaching for the network instead of the cache.
"""

import re
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
GO_ANALYZER_DIR = PIPELINE_ROOT / "Dockerfiles" / "codeql" / "go"
BUILDER_ENTRYPOINT = PIPELINE_ROOT / "Dockerfiles" / "builder" / "builder-entrypoint.sh"

SHARED_MODULE_CACHE = "/workspace/.gomodcache"


def test_builder_writes_the_module_cache_where_the_analyzer_can_read_it():
    """An analyzer container inherits the builder's volumes, not its filesystem."""
    content = BUILDER_ENTRYPOINT.read_text(encoding="utf-8")
    assert re.search(r'^export GOMODCACHE="\$\{PROJECT_ROOT\}/\.gomodcache"$', content, re.M)
    # It has to be exported before the project script runs, or that script's downloads miss it.
    assert content.index("export GOMODCACHE=") < content.index("source ./project_config.sh")


def test_analyzer_reads_that_same_cache_and_stays_offline():
    content = (GO_ANALYZER_DIR / "analyze.sh").read_text(encoding="utf-8")
    assert f'GOMODCACHE_DIR="{SHARED_MODULE_CACHE}"' in content
    assert 'export GOMODCACHE="$GOMODCACHE_DIR"' in content
    assert 'export GOPROXY="off"' in content
    # Private modules have no public checksum entry; without this the cached copy is rejected.
    assert 'export GOPRIVATE="*"' in content
    # The cache must be set up before the build CodeQL observes, not after.
    assert content.index("GOMODCACHE_DIR=") < content.index("codeql database create")


def test_the_image_ships_a_go_new_enough_to_build_real_projects():
    """Ubuntu's golang-go is 1.18 and rejects every go.mod that declares a newer language."""
    content = (GO_ANALYZER_DIR / "Dockerfile").read_text(encoding="utf-8")
    instructions = "\n".join(
        line for line in content.splitlines() if not line.lstrip().startswith("#")
    )
    assert "golang-go" not in instructions

    go_versions = re.findall(r"^ARG GO_VERSION=(\S+)$", content, re.M)
    assert len(go_versions) == 1
    major, minor, _patch = go_versions[0].split(".")
    assert (int(major), int(minor)) >= (1, 24), go_versions[0]

    assert 'curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"' in content
    # A go.mod newer than the image resolves its toolchain from the shared cache; 'local' would
    # fail instead, and an unset value is 'auto' only by today's default.
    assert re.search(r"^ENV GOTOOLCHAIN=auto$", content, re.M)
