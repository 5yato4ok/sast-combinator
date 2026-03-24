FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY mcp_server.py .
COPY context_extractor ./context_extractor
COPY pytest.ini .
COPY tests ./tests

EXPOSE 8080
EXPOSE 8000

# Default: run MCP server. Override with CMD to run legacy Flask app.
CMD ["python", "mcp_server.py"]
