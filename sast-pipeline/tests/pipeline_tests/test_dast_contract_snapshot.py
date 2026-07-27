import json
from copy import deepcopy

import pytest

from pipeline.dast.contract_snapshot import (
    CONTRACT_PATH,
    DastContractCompatibilityError,
    DastContractSnapshot,
)


def _snapshot():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_pinned_provider_contract_is_compatible_with_onboarding_and_runtime_connector():
    snapshot = DastContractSnapshot.load()

    assert snapshot["info"]["version"] == "2.0"
    assert not any(path.startswith("/integrations/v1/") for path in snapshot["paths"])


def test_removed_runtime_response_field_is_a_breaking_change():
    snapshot = deepcopy(_snapshot())
    del snapshot["components"]["schemas"]["V2RunStatusSchema"]["properties"]["result_ready"]

    with pytest.raises(DastContractCompatibilityError, match="V2RunStatusSchema fields changed"):
        DastContractSnapshot.validate(snapshot)


def test_removed_v2_path_is_a_breaking_change():
    snapshot = deepcopy(_snapshot())
    del snapshot["paths"]["/integrations/v2/runs/{run_id}/results"]

    with pytest.raises(DastContractCompatibilityError, match="path set"):
        DastContractSnapshot.validate(snapshot)


def test_error_envelope_and_supported_codes_are_part_of_the_contract():
    snapshot = deepcopy(_snapshot())
    snapshot["components"]["schemas"]["V2ErrorSchema"]["properties"]["code"]["enum"].remove("SOURCE_DRIFT")

    with pytest.raises(DastContractCompatibilityError, match="error-code set"):
        DastContractSnapshot.validate(snapshot)
