FROM ubuntu:24.04

# Install dependencies and .NET SDK 8.0
RUN apt-get update && \
    apt-get install -y wget apt-transport-https software-properties-common gnupg ca-certificates && \
    wget https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -y dotnet-sdk-8.0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install DevSkim CLI as a .NET global tool
RUN dotnet tool install -g Microsoft.CST.DevSkim.CLI

# Add dotnet tools directory to PATH
ENV PATH="${PATH}:/root/.dotnet/tools"

# Working directory for source code
WORKDIR /src

# Copy analysis script
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

# Entrypoint: run script
ENTRYPOINT ["/analyze.sh"]

# Default command: analyze /src and write results to /src/devskim.sarif
CMD ["devskim", "analyze", "-I", "/src", "--output-format", "sarif", "-O", "/src/devskim_results.sarif"]
