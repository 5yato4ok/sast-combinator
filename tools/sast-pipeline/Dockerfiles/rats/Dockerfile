FROM debian:bookworm-slim

# Install basic dependencies
RUN apt-get update && apt-get install -y \
    curl file git sudo build-essential ca-certificates procps \
 && rm -rf /var/lib/apt/lists/*

# Install Homebrew via official script
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Set up Homebrew environment
ENV PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"
ENV HOMEBREW_NO_AUTO_UPDATE=1

# Install RATS via Homebrew
RUN brew install rats

# Set working directory
WORKDIR /workspace

# Copy analyzer wrapper script
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

# Entrypoint
ENTRYPOINT ["/analyze.sh"]
