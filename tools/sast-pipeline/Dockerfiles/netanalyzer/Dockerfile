FROM mcr.microsoft.com/dotnet/sdk:8.0
RUN apt-get update && apt-get install -y --no-install-recommends bash git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY analyze.sh /app/analyze.sh
RUN chmod +x /app/analyze.sh
ENTRYPOINT ["/app/analyze.sh"]
