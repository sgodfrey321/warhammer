from __future__ import annotations

import os
import shutil
import urllib.parse
from pathlib import Path
from typing import Protocol

import requests

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"


class HttpSession(Protocol):
    def get(self, url: str, **kwargs) -> requests.Response: ...


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def latest_commit_sha(org: str, repo: str, branch: str, session: HttpSession) -> str:
    url = f"{GITHUB_API}/repos/{org}/{repo}/commits/{branch}"
    resp = session.get(url, headers=_github_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()["sha"]


def raw_url(org: str, repo: str, path: str, branch: str) -> str:
    # Real filenames contain spaces, apostrophes, and commas (e.g. "Chaos - Emperor's
    # Children.json", "Warhammer 40,000.json") -- must be quoted per path segment.
    quoted = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return f"{RAW_BASE}/{org}/{repo}/{branch}/{quoted}"


class RepoCache:
    """Caches raw files pulled from one GitHub repo, keyed by that repo's latest commit sha
    on `branch` so an unchanged repo is never re-downloaded."""

    def __init__(
        self,
        cache_dir: Path,
        org: str,
        repo: str,
        branch: str = "main",
        *,
        session: HttpSession | None = None,
    ):
        self.org = org
        self.repo = repo
        self.branch = branch
        self.session = session or requests.Session()
        self.dir = Path(cache_dir) / f"{org}__{repo}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._sha_file = self.dir / ".sha"

    def refresh(self, *, force: bool = False) -> bool:
        """Check the repo's latest commit sha against what's cached; wipe cached files if it
        changed (or `force` is set). Returns True if the cache was invalidated."""
        sha = latest_commit_sha(self.org, self.repo, self.branch, self.session)
        cached_sha = self._sha_file.read_text().strip() if self._sha_file.exists() else None
        stale = force or cached_sha != sha
        if stale:
            for child in self.dir.iterdir():
                if child == self._sha_file:
                    continue
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            self._sha_file.write_text(sha)
        return stale

    def get(self, path: str) -> bytes:
        """Return the raw bytes of `path` in this repo, from cache when present."""
        cache_path = self.dir / path
        if cache_path.exists():
            return cache_path.read_bytes()
        url = raw_url(self.org, self.repo, path, self.branch)
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
        return resp.content

    def list_files(self, *, path: str = "") -> list[str]:
        """File names at `path` via the GitHub contents API. Not cached -- this is a listing
        call, cheap relative to downloading file bodies, and needs to see new/removed files
        even when the sha-based file cache above hasn't been invalidated for other reasons."""
        url = f"{GITHUB_API}/repos/{self.org}/{self.repo}/contents/{path}"
        resp = self.session.get(url, headers=_github_headers(), timeout=30)
        resp.raise_for_status()
        return [item["name"] for item in resp.json() if item["type"] == "file"]
