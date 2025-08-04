FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    git \
    g++ \
    cmake \
    make \
    python3 \
    wget \
    unzip \
    libtinyxml2-dev \
    libpcre3-dev \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Build cppcheck from sources, to be sure about tool version
WORKDIR /opt
RUN git clone --branch 2.17.1 https://github.com/danmar/cppcheck.git && \
    cd cppcheck && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release -DHAVE_RULES=ON && \
    make -j$(nproc) && \
    make install


WORKDIR /src

# Default values
CMD ["cppcheck", "--output-format=sarif", "--output-file=cppcheck_result.sarif", "--check-level=exhaustive", "-j", "4", "."]
