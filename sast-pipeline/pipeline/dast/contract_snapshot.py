"""Offline compatibility gate for the provider-owned DAST OpenAPI v2 snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "dast-integration.openapi.json"
SOURCE_PATH = PROJECT_ROOT / "contracts" / "dast-integration.source.json"


class DastContractCompatibilityError(ValueError):

    """The pinned provider artifact is missing a consumer requirement."""


class DastContractSnapshot:
    PATH_OPERATIONS: ClassVar[dict[str, tuple[str, str, str]]] = {
        "/integrations/v2/ping": ("get", "200", "V2PingResponseSchema"),
        "/integrations/v2/targets": ("get", "200", "V2TargetsResponseSchema"),
        "/integrations/v2/runs": ("post", "202", "V2RunAcceptedSchema"),
        "/integrations/v2/runs/{run_id}": ("get", "200", "V2RunStatusSchema"),
        "/integrations/v2/runs/{run_id}/logs": ("get", "200", "V2LogsResponseSchema"),
        "/integrations/v2/runs/{run_id}/results": ("get", "200", "V2TerminalResultSchema"),
        "/integrations/v2/runs/{run_id}/stop": ("post", "200", "V2StopResponseSchema"),
    }
    SCHEMA_FIELDS: ClassVar[dict[str, frozenset[str]]] = {
        "V2PingResponseSchema": frozenset({"contract_version", "gateway_version", "status"}),
        "V2TargetsResponseSchema": frozenset({"contract_version", "etag", "targets"}),
        "V2TargetSchema": frozenset(
            {
                "id",
                "display_name",
                "contract_revision",
                "capability_revision",
                "schema_digest",
                "parameter_schema",
                "defaults",
                "repository_keys",
                "launch_requirements",
                "autonomous_ready",
            },
        ),
        "V2RunAcceptedSchema": frozenset({"contract_version", "run_id", "correlation_id", "status"}),
        "V2RunStatusSchema": frozenset(
            {"contract_version", "run_id", "correlation_id", "status", "selection", "error_code", "result_ready"},
        ),
        "V2LogEventSchema": frozenset({"event_id", "level", "message", "timestamp"}),
        "V2LogsResponseSchema": frozenset({"contract_version", "events", "next_cursor", "has_more"}),
        "V2StopResponseSchema": frozenset(
            {
                "contract_version",
                "run_id",
                "correlation_id",
                "status",
                "selection",
                "error_code",
                "result_ready",
                "stop_requested",
            },
        ),
        "V2TerminalResultSchema": frozenset(
            {
                "contract_version",
                "run_id",
                "status",
                "selection",
                "trigger_resolution",
                "dast_run_metadata",
                "report",
                "audit",
            },
        ),
        "V2ErrorSchema": frozenset({"code", "message", "retryable", "correlation_id"}),
    }
    REQUIRED_ERROR_CODES: ClassVar[frozenset[str]] = frozenset(
        {
            "INVALID_REQUEST",
            "AUTHENTICATION_FAILED",
            "POLICY_DENIED",
            "UNKNOWN_RUN",
            "IDEMPOTENCY_CONFLICT",
            "CAPACITY_BUSY",
            "CAPABILITY_REVISION_MISMATCH",
            "RUN_NOT_TERMINAL",
            "NO_ELIGIBLE_STAND",
            "SOURCE_DRIFT",
            "REPORT_MISSING",
            "REPORT_INVALID",
            "AUDIT_INCOMPLETE",
            "RESPONSE_TOO_LARGE",
            "RATE_LIMITED",
            "INTERNAL_ERROR",
        },
    )

    @classmethod
    def load(cls, path: Path = CONTRACT_PATH, source_path: Path = SOURCE_PATH) -> dict[str, Any]:
        artifact_bytes = path.read_bytes()
        source = json.loads(source_path.read_text(encoding="utf-8"))
        checksum = hashlib.sha256(artifact_bytes).hexdigest()
        if source.get("artifact_sha256") != checksum:
            message = "DAST OpenAPI artifact checksum does not match its source record"
            raise DastContractCompatibilityError(message)
        snapshot = json.loads(artifact_bytes)
        cls.validate(snapshot)
        return snapshot

    @classmethod
    def validate(cls, snapshot: object) -> None:
        if not isinstance(snapshot, dict) or snapshot.get("openapi") != "3.1.0":
            message = "DAST contract must be an OpenAPI 3.1 object"
            raise DastContractCompatibilityError(message)
        if snapshot.get("info", {}).get("version") != "2.0":
            message = "DAST contract must be exactly version 2.0"
            raise DastContractCompatibilityError(message)
        paths = snapshot.get("paths")
        if not isinstance(paths, dict) or set(paths) != set(cls.PATH_OPERATIONS):
            message = "DAST v2 path set does not match the supported contract"
            raise DastContractCompatibilityError(message)
        for path, (method, success_status, schema_name) in cls.PATH_OPERATIONS.items():
            cls._validate_operation(paths[path], path, method, success_status, schema_name)

        schemas = snapshot.get("components", {}).get("schemas", {})
        for schema_name, expected_fields in cls.SCHEMA_FIELDS.items():
            actual_fields = set(schemas.get(schema_name, {}).get("properties", {}))
            if actual_fields != expected_fields:
                message = f"DAST schema {schema_name} fields changed"
                raise DastContractCompatibilityError(message)

        request_schema = schemas.get("V2RunRequestSchema", {})
        request_fields = set(request_schema.get("properties", {}))
        expected_request_fields = {
            "contract_version",
            "idempotency_key",
            "correlation_id",
            "target_id",
            "capability_revision",
            "trigger",
            "parameters",
        }
        if request_fields != expected_request_fields:
            message = "DAST start request fields changed"
            raise DastContractCompatibilityError(message)
        trigger_types = {
            variant.get("properties", {}).get("type", {}).get("const")
            for variant in request_schema.get("properties", {}).get("trigger", {}).get("oneOf", [])
        }
        if not {"GIT_BRANCH", "GIT_HASH"}.issubset(trigger_types):
            message = "DAST no longer supports the AIST trigger types"
            raise DastContractCompatibilityError(message)

        error_codes = set(schemas.get("V2ErrorSchema", {}).get("properties", {}).get("code", {}).get("enum", []))
        if not cls.REQUIRED_ERROR_CODES.issubset(error_codes):
            message = "DAST typed error-code set is incomplete"
            raise DastContractCompatibilityError(message)

        metadata_schema = schemas.get("V2RunMetadataSchema", {})
        source_schema = metadata_schema.get("properties", {}).get("source_commits", {})
        if (
            metadata_schema.get("additionalProperties") is not True
            or "source_commits" not in metadata_schema.get("required", [])
            or source_schema.get("type") != "object"
            or source_schema.get("additionalProperties", {}).get("type") != "string"
        ):
            message = "DAST terminal metadata lost its typed required source claim or extension point"
            raise DastContractCompatibilityError(message)
        terminal_statuses = set(
            schemas.get("V2TerminalResultSchema", {})
            .get("properties", {}).get("status", {}).get("enum", [])
        )
        if terminal_statuses != {
            "succeeded", "completed_with_degradation", "failed_with_partial_results", "failed", "stopped",
        }:
            message = "DAST terminal status set changed"
            raise DastContractCompatibilityError(message)

    @classmethod
    def _validate_operation(
        cls,
        path_item: object,
        path: str,
        method: str,
        success_status: str,
        schema_name: str,
    ) -> None:
        operation = path_item.get(method) if isinstance(path_item, dict) else None
        if not isinstance(operation, dict) or operation.get("security") != [{"BearerAuth": []}]:
            message = f"DAST operation {method.upper()} {path} lost bearer security"
            raise DastContractCompatibilityError(message)
        responses = operation.get("responses", {})
        cls._require_schema_ref(responses.get(success_status), schema_name, f"{method.upper()} {path} success")
        for status, response in responses.items():
            if status != success_status:
                cls._require_schema_ref(response, "V2ErrorSchema", f"{method.upper()} {path} error {status}")

    @staticmethod
    def _require_schema_ref(response: object, schema_name: str, location: str) -> None:
        if not isinstance(response, dict):
            message = f"DAST response is missing for {location}"
            raise DastContractCompatibilityError(message)
        schema = response.get("content", {}).get("application/json", {}).get("schema")
        if schema != {"$ref": f"#/components/schemas/{schema_name}"}:
            message = f"DAST response schema changed for {location}"
            raise DastContractCompatibilityError(message)
