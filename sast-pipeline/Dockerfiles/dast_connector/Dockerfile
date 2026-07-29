FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS runtime

WORKDIR /app

RUN pip install --no-cache-dir httpx==0.28.1

COPY pipeline/__init__.py pipeline/docker_utils.py /app/pipeline/
COPY pipeline/dast/ /app/pipeline/dast/

USER 1001:1001

ENTRYPOINT ["python", "-m", "pipeline.dast.connector"]

FROM runtime AS test

USER root

RUN pip install --no-cache-dir pytest==8.4.2 pyyaml==6.0.3

COPY pipeline/config_utils.py /app/pipeline/config_utils.py
COPY pipeline/cli.py /app/pipeline/cli.py
COPY pipeline/contracts.py /app/pipeline/contracts.py
COPY pipeline/execution.py /app/pipeline/execution.py
COPY pipeline/registry.py /app/pipeline/registry.py
COPY pipeline/sast_execution.py /app/pipeline/sast_execution.py
COPY pipeline/project_builder.py /app/pipeline/project_builder.py
COPY pipeline/agent_bridge_runner.py /app/pipeline/agent_bridge_runner.py
COPY pipeline/bridge_client.py /app/pipeline/bridge_client.py
COPY pipeline/analyzer_runner.py /app/pipeline/analyzer_runner.py
COPY pipeline/config/ /app/pipeline/config/
COPY contracts/ /app/contracts/
COPY run_pipeline.py /app/run_pipeline.py
COPY tests/pipeline_tests/test_analyzers_yaml_dast.py /app/tests/pipeline_tests/test_analyzers_yaml_dast.py
COPY tests/pipeline_tests/test_dast_contract_snapshot.py /app/tests/pipeline_tests/test_dast_contract_snapshot.py
COPY tests/pipeline_tests/test_dast_connector.py /app/tests/pipeline_tests/test_dast_connector.py
COPY tests/pipeline_tests/test_dast_executor.py /app/tests/pipeline_tests/test_dast_executor.py
COPY tests/pipeline_tests/test_execution_registry.py /app/tests/pipeline_tests/test_execution_registry.py

USER 1001:1001

ENTRYPOINT ["python", "-m", "pytest"]

FROM runtime AS production
