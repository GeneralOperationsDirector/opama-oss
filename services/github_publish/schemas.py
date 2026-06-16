from typing import Optional
from pydantic import BaseModel


class GitHubPublishSettingsIn(BaseModel):
    repo: Optional[str] = None
    file_path: Optional[str] = None
    commit_message: Optional[str] = None
    # Blank/omitted = keep the existing token
    token: Optional[str] = None


class GitHubPublishSettingsOut(BaseModel):
    repo: Optional[str] = None
    file_path: Optional[str] = None
    commit_message: Optional[str] = None
    # Token is never returned in full — only a masked hint and a boolean
    token_set: bool = False
    token_hint: Optional[str] = None


class GitHubTestRequest(BaseModel):
    # Both optional — fall back to the saved settings when omitted, so the
    # button works both for unsaved edits and already-configured settings.
    token: Optional[str] = None
    repo: Optional[str] = None


class GitHubTestResult(BaseModel):
    connected: bool
    repo_full_name: Optional[str] = None
    private: Optional[bool] = None
    can_push: Optional[bool] = None
    error: Optional[str] = None
