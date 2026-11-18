#!/bin/bash
set -euo pipefail

export PROJECT_PATH=/workspace/source
mkdir -p "$PROJECT_PATH"
printf '{"jobs":%s}\n' "$JOBS" > /shared/output/build-environment.json
if [[ "${FIXTURE_SOURCE_ONLY:-0}" == 1 ]]; then
    printf 'int main() { return 0; }\n' > "$PROJECT_PATH/main.cpp"
    export NON_COMPILE_PROJECT=1
    return
fi

apt-get update -qq
apt-get install -y --no-install-recommends g++ cmake make

# This compiler path exists only in the initialized builder's filesystem.
mkdir -p /usr/local/project-toolchain/bin /workspace/source
ln -s /usr/bin/g++ /usr/local/project-toolchain/bin/g++
export PATH="/usr/local/project-toolchain/bin:$PATH"
export CXX=g++
export CXXFLAGS=-DPROJECT_INIT_COMPLETED
export NON_COMPILE_PROJECT=0

cat > "$PROJECT_PATH/CMakeLists.txt" <<'CMAKE'
cmake_minimum_required(VERSION 3.16)
project(capture_fixture LANGUAGES CXX)
add_library(component STATIC component.cpp)
add_executable(application main.cpp)
target_link_libraries(application component)
CMAKE
cat > "$PROJECT_PATH/component.cpp" <<'CPP'
#include <cstdlib>
#ifndef PROJECT_INIT_COMPLETED
#error Project initialization environment was lost
#endif
void release_twice() {
    void* value = malloc(16);
    free(value);
    free(value);
}
CPP
cat > "$PROJECT_PATH/main.cpp" <<'CPP'
void release_twice();
int main() { release_twice(); }
CPP

cmake -S "$PROJECT_PATH" -B "$PROJECT_PATH/build"
# Expand JOBS when the captured build runs.
# shellcheck disable=SC2016
export SAST_BUILD_COMMAND='cmake --build build --clean-first --target component application --parallel "$JOBS"'
