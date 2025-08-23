"""
DefectDojo refactor (strict): identical REST calls, reorganized into classes.
- DefectDojoClient: generic helpers (session, products, engagements, findings, metadata)
- SastPipelineDDClient: SAST pipeline logic (engagement naming, upload+trim+enrich)
- api: backward-compatible function layer (same signatures as original module)
All comments are in English.
"""
from .client import DefectDojoClient, DojoConfig, ImportResult
from .sast_client import SastPipelineDDClient
