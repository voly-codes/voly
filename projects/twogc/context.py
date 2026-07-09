"""Shared paths and template tokens for 2GC / MTS B2B Store missions."""
from __future__ import annotations

import os

TGC_ROOT = os.environ.get("TGC_ROOT", "/home/lanies/git/2GC")
MTS_2GC = os.environ.get("MTS_2GC_PATH", f"{TGC_ROOT}/mts-2gc")
RELAY_INSTALLER = os.environ.get(
    "RELAY_INSTALLER_PATH", f"{TGC_ROOT}/cloudbridge-relay-installer"
)
CLOUDBRIDGE_CLIENT = os.environ.get(
    "CLOUDBRIDGE_CLIENT_PATH", f"{TGC_ROOT}/cloudbridge-client"
)
CLOUDBRIDGE_DOCS = os.environ.get(
    "CLOUDBRIDGE_DOCS_PATH", f"{TGC_ROOT}/cloudbridge-docs"
)

BUNDLE_ROOT = f"{MTS_2GC}/bundle/cloudbridge-relay"
BUNDLE_BUILD = f"{BUNDLE_ROOT}/BUILD.md"
ACCESS_DOC = f"{MTS_2GC}/docs/ACCESS.md"
B2BSTORE_DOCS = "https://stage.b2bstore.mws.ru/docs/"
B2BSTORE_API = "https://stage.b2bstore.mws.ru/api/v1"
ARTIFACTORY_ENDPOINT = "https://stage.b2bstore.mws.ru/a"

TGC_REF = (
    f"2GC monorepo: {TGC_ROOT}\n"
    f"MTS integration: {MTS_2GC}\n"
    f"Relay installer (source stack): {RELAY_INSTALLER}\n"
    f"B2B Store bundle skeleton: {BUNDLE_ROOT}\n"
    f"Vendor API docs: {ACCESS_DOC}\n"
    f"Platform docs: {B2BSTORE_DOCS}"
)

TGC_SYSTEM = f"""You are implementing CloudBridge deployment for MWS B2B Store (vendor gc2, stage).

Read first:
- {ACCESS_DOC}
- {BUNDLE_BUILD}
- {TGC_ROOT}/cloudbridge-docs/ARCHITECTURE/OVERVIEW/PROJECT_OVERVIEW.md

Rules:
- Minimal focused diffs; match existing conventions in each repo
- Never commit .env or secrets
- B2B Store bundle format: product.yaml, artifacts.yaml, plans/*/manifest/*.tf
- Terraform for marketplace must NOT declare provider blocks
- VMware backend type: vcd (see backends.yaml)
- Test with: python3 {MTS_2GC}/scripts/b2bstore.py
- OVA upload uses Artifactory CLI at {ARTIFACTORY_ENDPOINT}
"""


def mission_context() -> dict[str, str]:
    return {
        k: v
        for k, v in globals().items()
        if k.isupper() and isinstance(v, str)
    }
