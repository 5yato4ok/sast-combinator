"""Command-line boundary for ``run_pipeline.py dast`` standalone executions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.config_utils import AnalyzersConfigHelper
from pipeline.dast.contracts import DastRecoveryState, DastStartCommand
from pipeline.dast.executor import DastExecutionInput, DastExecutionResult
from pipeline.execution import DAST_EXECUTION_TYPE, execute_pipeline

_MAX_COMMAND_BYTES = 1024 * 1024


def _command_from_file(path: Path) -> DastStartCommand:
    if path.stat().st_size > _MAX_COMMAND_BYTES:
        raise ValueError("DAST command file exceeds its size limit")
    return DastStartCommand.from_wire(json.loads(path.read_text(encoding="utf-8")))


def run(argv: list[str], *, analyzer_config: AnalyzersConfigHelper) -> DastExecutionResult:
    parser = argparse.ArgumentParser(description="Run the shared-catalog standalone DAST execution")
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--command-file", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--recovery-file", type=Path)
    parser.add_argument("--vpn-container")
    parser.add_argument("--stop-requested", action="store_true")
    args = parser.parse_args(argv)

    command = _command_from_file(args.command_file)
    recovery = DastRecoveryState.from_file(args.recovery_file) if args.recovery_file else None
    result = execute_pipeline(
        DAST_EXECUTION_TYPE,
        DastExecutionInput(
            pipeline_id=args.pipeline_id,
            gateway_url=args.gateway_url.rstrip("/"),
            command=command,
            workspace=args.workspace,
            output_dir=args.output_dir,
            token_file=args.token_file,
            recovery=recovery,
            ca_file=args.ca_file,
            vpn_container_name=args.vpn_container,
            stop_requested=args.stop_requested,
        ),
        analyzer_config=analyzer_config,
    )
    payload = result.terminal_result.to_wire() if result.terminal_result else result.outcome.to_wire()
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return result
