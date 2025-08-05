FROM python:3.12-slim

# Install flawfinder
RUN pip install --no-cache-dir flawfinder

# Set working directory
WORKDIR /src

# Copy analyzer script
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

# Set entrypoint to script
ENTRYPOINT ["/analyze.sh"]
