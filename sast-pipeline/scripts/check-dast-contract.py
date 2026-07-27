#!/usr/bin/env python3
"""Validate the pinned provider contract without network or a provider checkout."""

from pipeline.dast.contract_snapshot import DastContractSnapshot


if __name__ == "__main__":
    DastContractSnapshot.load()
