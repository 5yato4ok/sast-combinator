FROM python:3.12-slim


RUN pip install --no-cache-dir flawfinder

WORKDIR /src

VOLUME /src

CMD ["sh", "-c", "flawfinder --sarif . > flawfinder_results.sarif"]
