"""Single source of truth for opama's core version.

Read by app.main (FastAPI app version), services/system (api_version), and
app.plugin_loader (requires_core compatibility checks). Bump alongside
CHANGELOG.md and the matching git tag — see docs/RELEASE_PROCESS.md.
"""

CORE_VERSION = "0.2.0"
