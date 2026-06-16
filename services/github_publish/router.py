"""
GitHub Publishing API router — mounted at /integrations/github.

Per-user GitHub repo/file-path/commit-message config (plugin_data) and PAT
(user_secret, service "github_publish_token"). Settings + connection test
live here; external_plugins/opama_storefront/router.py's publish flow calls
`get_publish_config()`/`commit_file()` from .client to do the actual commit.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from services.shared.plugin_data import get_user_plugin_data, set_user_plugin_data
from services.shared.user_secrets import get_user_secret, set_user_secret, user_secret_status

from .client import PLUGIN_ID, SECRET_SERVICE, DEFAULT_COMMIT_MESSAGE, test_connection
from .schemas import (
    GitHubPublishSettingsIn,
    GitHubPublishSettingsOut,
    GitHubTestRequest,
    GitHubTestResult,
)

router = APIRouter(prefix="/integrations/github", tags=["github_publish"])


@router.get("/settings", response_model=GitHubPublishSettingsOut)
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = get_user_plugin_data(session, PLUGIN_ID, current_user.id)
    token_set, token_hint = user_secret_status(session, current_user.id, SECRET_SERVICE)
    return GitHubPublishSettingsOut(
        repo=data.get("repo"),
        file_path=data.get("file_path"),
        commit_message=data.get("commit_message") or DEFAULT_COMMIT_MESSAGE,
        token_set=token_set,
        token_hint=token_hint,
    )


@router.put("/settings", response_model=GitHubPublishSettingsOut)
def update_settings(
    body: GitHubPublishSettingsIn,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    set_user_plugin_data(
        session, PLUGIN_ID, current_user.id,
        repo=body.repo, file_path=body.file_path, commit_message=body.commit_message,
    )
    token_changed = bool(body.token)
    if token_changed:
        set_user_secret(session, current_user.id, SECRET_SERVICE, body.token)

    write_audit_log(
        session,
        action="github_publish.settings_update",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        detail="updated settings" + ("; token changed" if token_changed else ""),
    )

    return get_settings(session=session, current_user=current_user)


@router.post("/test", response_model=GitHubTestResult)
def test(
    body: GitHubTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Verify a GitHub token can read/write the given repo.

    Accepts an unsaved token/repo from the form so the button works before
    the user clicks Save, falling back to the stored settings otherwise.
    """
    data = get_user_plugin_data(session, PLUGIN_ID, current_user.id)
    repo = body.repo or data.get("repo")
    token = body.token or get_user_secret(session, current_user.id, SECRET_SERVICE)

    if not repo or not token:
        raise HTTPException(422, "GitHub token and repository are required")

    return test_connection(token, repo)
