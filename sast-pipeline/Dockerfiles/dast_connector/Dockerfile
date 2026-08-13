FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS runtime

WORKDIR /app

RUN pip install --no-cache-dir httpx==0.28.1

COPY pipeline/__init__.py pipeline/docker_utils.py /app/pipeline/
COPY pipeline/dast/ /app/pipeline/dast/

USER 1001:1001

ENTRYPOINT ["python", "-m", "pipeline.dast.connector"]

FROM runtime AS test

USER root

# httpx is needed by bridge_client, which several of the copied tests import.
RUN pip install --no-cache-dir pytest==8.4.2 pyyaml==6.0.3 httpx==0.28.1

# The whole package and the whole test tree, not a hand-picked list. Naming individual files is
# how most of tests/pipeline_tests/ ended up outside CI: the job could run the directory and
# still cover only what the image happened to contain. The runtime stage above stays minimal --
# this is only the test stage.
COPY pipeline/ /app/pipeline/
COPY contracts/ /app/contracts/
COPY run_pipeline.py /app/run_pipeline.py
COPY tests/ /app/tests/

USER 1001:1001

ENTRYPOINT ["python", "-m", "pytest"]

FROM runtime AS production
