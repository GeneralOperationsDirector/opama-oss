"""
GitHub Contents API client + per-user settings accessor.

Used by this module's own router (settings + connection test) and by
external_plugins/opama_storefront/router.py's publish flow
(`get_publish_config()` + `commit_file()`). No FastAPI imports — safe to
call from any module's route handlers.

Settings live in the core `plugin_data`/`user_secret` tables
(services/shared/plugin_data.py, services/shared/user_secrets.py) — see
docs/MODULE_DEVELOPMENT.md §4(A). No dedicated table for this module.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlmodel import Session

from services.shared.plugin_data import get_user_plugin_data
from services.shared.user_secrets import get_user_secret
from .schemas import GitHubTestResult

PLUGIN_ID = "github_publish"
SECRET_SERVICE = f"{PLUGIN_ID}_token"
DEFAULT_COMMIT_MESSAGE = "chore: publish catalog ({n} items)"

_GITHUB_API = "https://api.github.com"


@dataclass
class GitHubPublishConfig:
    repo: str
    file_path: str
    commit_message: str
    token: str


def github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def commit_file(
    token: str,
    repo: str,
    file_path: str,
    content: str,
    commit_message: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Commit content to a file in a GitHub repo via the Contents API.
    Returns (success, commit_html_url, error_message).
    """
    url = f"{_GITHUB_API}/repos/{repo}/contents/{file_path}"
    headers = github_headers(token)

    # Fetch current SHA (required to update an existing file)
    sha: Optional[str] = None
    get_resp = httpx.get(url, headers=headers, timeout=15)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
    elif get_resp.status_code == 404:
        pass  # File doesn't exist yet — create it
    else:
        return False, None, f"GitHub GET failed: {get_resp.status_code} {get_resp.text[:200]}"

    body: dict = {
        "message": commit_message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        body["sha"] = sha

    put_resp = httpx.put(url, headers=headers, json=body, timeout=15)
    if put_resp.status_code in (200, 201):
        commit_url = put_resp.json().get("commit", {}).get("html_url")
        return True, commit_url, None
    else:
        return False, None, f"GitHub PUT failed: {put_resp.status_code} {put_resp.text[:300]}"


def test_connection(token: str, repo: str) -> GitHubTestResult:
    """Verify a GitHub token can read/write the given repo via GET /repos/{repo}."""
    resp = httpx.get(f"{_GITHUB_API}/repos/{repo}", headers=github_headers(token), timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return GitHubTestResult(
            connected=True,
            repo_full_name=data.get("full_name"),
            private=data.get("private"),
            can_push=data.get("permissions", {}).get("push", False),
        )
    if resp.status_code == 401:
        return GitHubTestResult(connected=False, error="GitHub token is invalid or expired")
    if resp.status_code == 404:
        return GitHubTestResult(connected=False, error=f"Repository '{repo}' not found, or the token lacks access to it")
    return GitHubTestResult(connected=False, error=f"GitHub API error: {resp.status_code}")


def get_publish_config(session: Session, user_id: int) -> Optional[GitHubPublishConfig]:
    """Return the user's GitHub publish config, or None unless repo, file_path, and token are ALL set."""
    data = get_user_plugin_data(session, PLUGIN_ID, user_id)
    repo = data.get("repo")
    file_path = data.get("file_path")
    token = get_user_secret(session, user_id, SECRET_SERVICE)
    if not (repo and file_path and token):
        return None
    return GitHubPublishConfig(
        repo=repo,
        file_path=file_path,
        commit_message=data.get("commit_message") or DEFAULT_COMMIT_MESSAGE,
        token=token,
    )
