"""The shape of a pipeline log line, pinned against a real run.

Fixture: the DAST connector's own output from run ``844118b8`` (2026-10-04), written to the
contract the connector emits against -- level, then the phase and job it is working on.
What this guards is the scenario, not the parser: an operator opening the log of a failed
run must be able to list the failed jobs and the stage that refused to advance from the
ERROR lines alone.
"""

import logging

import pytest

import pipeline.docker_utils as du


RUN_844118B8 = """\
[INFO] run admitted: run=844118b86b4c6304d89c09b26b5d4de0 root=/home/user/dast/runtime
[INFO][p0] launch resolved: target=nxlicensed scenario=source-driven tier=test depth=deep
[ERROR][p0] sso: token expired and refresh failed
[WARNING][p0] access unavailable: aws:cloud-prod, aws:cloud-test
[INFO][p0/recon-collect] job start: kind=mechanical attempt=1
[WARNING][p0/recon-collect] shodan:nxlicensed.hdw.mx failed: api key not initialised
[INFO][p0/recon-collect] job ok: attempt=1 dur=177s
[INFO][p1/provision-accounts] job start: kind=troubleshoot attempt=1
[ERROR][p1/provision-accounts] job give-up: attempts=3/3 failed the same way
[INFO][p1/account-preconditions] job start: kind=mechanical attempt=1
[WARNING][p1/account-preconditions] credential refs unresolved: lic-admin@test, lic-user@test
[ERROR][p1/account-preconditions] job fail: attempt=1 exit=4 retry=requeue
[ERROR][p1] dispatch refused to advance the run: StageFailed phase-1-account-preconditions
[ERROR][p8/coverage] job fail: attempt=1 exit=3 retry=requeue
[INFO][p8/export] exported 0 finding(s) -> runs/844118b8/generic-aist-report.json
[ERROR][p8/audit] audit FAIL: no per-check records found
[ERROR][p8/audit] job fail: attempt=1 exit=2 dur=2s retry=requeue
[ERROR][p9/teardown] job fail: attempt=1 exit=4 retry=requeue
[INFO][p8/publish] triage board -> reports/triage.html
[ERROR] run failed: reason=stage_failed stage=p1/account-preconditions findings=0
"""


def _columns(message):
    """The bracketed columns a record opens with, and the message body after them."""
    columns = []
    rest = message
    while rest.startswith("["):
        token, rest = du._take_bracketed(rest)
        if token is None:
            break
        columns.append(token)
    return columns, rest.lstrip()


def _scope(record):
    columns, _ = _columns(record.getMessage())
    return columns[1] if len(columns) > 1 else None


@pytest.fixture
def relayed(caplog):
    """The run as it reaches the pipeline log, tagged with the analyzer's catalog name."""
    with caplog.at_level(logging.DEBUG, logger=du.log.name):
        for line in RUN_844118B8.splitlines():
            du._log_container_line(line, log_addition="[dast]")
    return caplog.records


def test_every_record_opens_with_its_source_and_nothing_wider(relayed):
    for record in relayed:
        message = record.getMessage()
        columns, body = _columns(message)
        assert columns[0] == "dast", message
        assert len(columns) <= 2, f"a third column crept in: {message}"
        assert body, message
        assert "2026-10-04" not in message


def test_the_failed_jobs_are_readable_from_the_error_lines_alone(relayed):
    """S3: open a failed run, grep ERROR, know what to fix without reading one INFO line."""
    failed = {
        _scope(record)
        for record in relayed
        if record.levelno >= logging.ERROR and "job " in record.getMessage()
    }
    assert failed == {
        "p1/provision-accounts",
        "p1/account-preconditions",
        "p8/coverage",
        "p8/audit",
        "p9/teardown",
    }


def test_the_run_ends_by_naming_the_stage_that_stopped_it(relayed):
    errors = [record.getMessage() for record in relayed if record.levelno >= logging.ERROR]
    assert any("StageFailed phase-1-account-preconditions" in message for message in errors)
    assert errors[-1] == (
        "[dast] run failed: reason=stage_failed stage=p1/account-preconditions findings=0"
    )


def test_a_warning_keeps_the_job_it_belongs_to(relayed):
    warned = {_scope(record) for record in relayed if record.levelno == logging.WARNING}
    assert warned == {"p0", "p0/recon-collect", "p1/account-preconditions"}
