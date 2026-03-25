FROM python:3.12-slim

WORKDIR /app

ARG BUILD_ENV=production
ENV DD_DEBUG=False
ENV DD_SECRET_KEY=changeme

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

USER appuser

CMD ["gunicorn", "app:create_app()"]
