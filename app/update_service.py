from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings

GITHUB_API = "https://api.github.com"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_dir_from_root(root: Path) -> Path | None:
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        try:
            content = dot_git.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return None
        if content.startswith("gitdir:"):
            path = content.split(":", 1)[1].strip()
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = (root / candidate).resolve()
            return candidate if candidate.exists() else None
    return None


def _read_ref_from_packed(git_dir: Path, ref_name: str) -> str | None:
    packed = git_dir / "packed-refs"
    if not packed.exists():
        return None
    try:
        for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            sha, ref = parts
            if ref.strip() == ref_name and len(sha) >= 7:
                return sha.strip()
    except Exception:
        return None
    return None


def _all_tag_refs(git_dir: Path) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    tags_root = git_dir / "refs" / "tags"
    if tags_root.exists():
        for path in tags_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                sha = path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                continue
            if not sha:
                continue
            try:
                rel = path.relative_to(tags_root).as_posix()
            except Exception:
                rel = path.name
            refs.append((rel, sha))

    packed = git_dir / "packed-refs"
    if packed.exists():
        try:
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    continue
                sha, ref = parts
                if not ref.startswith("refs/tags/"):
                    continue
                tag = ref.split("refs/tags/", 1)[1].strip()
                refs.append((tag, sha.strip()))
        except Exception:
            pass
    return refs


def detect_local_git_sha() -> str | None:
    root = _project_root()
    git_dir = _git_dir_from_root(root)
    if not git_dir:
        return None
    head = git_dir / "HEAD"
    if not head.exists():
        return None
    try:
        head_value = head.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
    if not head_value:
        return None
    if head_value.startswith("ref:"):
        ref_name = head_value.split(":", 1)[1].strip()
        ref_path = git_dir / ref_name
        if ref_path.exists():
            try:
                value = ref_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                value = ""
            if value:
                return value
        return _read_ref_from_packed(git_dir, ref_name)
    return head_value


def detect_local_tag_for_head() -> str | None:
    root = _project_root()
    git_dir = _git_dir_from_root(root)
    if not git_dir:
        return None
    head_sha = detect_local_git_sha()
    if not head_sha:
        return None
    matches = [tag for tag, sha in _all_tag_refs(git_dir) if sha.lower() == head_sha.lower()]
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0]


def _normalize_version(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]
    return value


def runtime_version_payload() -> dict:
    raw_version = (settings.app_version or "").strip()
    version_source = "env"
    if not raw_version or raw_version.lower() in {"dev", "unknown"}:
        local_tag = detect_local_tag_for_head()
        if local_tag:
            raw_version = local_tag
            version_source = "git_tag"
        else:
            raw_version = "dev"
            version_source = "fallback"

    build_sha = (settings.app_build_sha or "").strip()
    sha_source = "env"
    if not build_sha or build_sha == "unknown":
        git_sha = detect_local_git_sha()
        if git_sha:
            build_sha = git_sha
            sha_source = "git"
        else:
            build_sha = "unknown"
            sha_source = "unknown"

    source_repo = (settings.update_source_repo or "").strip().strip("/")
    repo_url = f"https://github.com/{source_repo}" if source_repo else ""
    tags_url = f"{repo_url}/tags" if repo_url else ""
    return {
        "version": raw_version,
        "versionSource": version_source,
        "buildSha": build_sha,
        "buildShaSource": sha_source,
        "buildTime": (settings.app_build_time or "").strip(),
        "displayVersion": raw_version,
        "sourceRepo": source_repo,
        "repoUrl": repo_url,
        "releaseUrl": tags_url,
        "updateWebhookConfigured": bool((settings.update_webhook_url or "").strip()),
    }


def _github_client_timeout() -> float:
    return float(max(settings.update_webhook_timeout, 3))


def _github_headers() -> dict:
    return {
        "accept": "application/vnd.github+json",
        "user-agent": "cloud-mail-vps-update-check",
    }


def fetch_latest_release() -> dict:
    if settings.update_check_url:
        with httpx.Client(timeout=_github_client_timeout()) as client:
            response = client.get(settings.update_check_url)
            response.raise_for_status()
            payload = response.json()
        tag = payload.get("tag") or payload.get("tagName") or payload.get("version") or ""
        return {
            "kind": "tag",
            "tag": tag,
            "name": payload.get("name") or tag,
            "display": tag,
            "url": payload.get("url") or payload.get("htmlUrl") or payload.get("html_url") or "",
            "publishedAt": payload.get("publishedAt") or payload.get("published_at") or "",
            "source": settings.update_check_url,
        }

    repo = (settings.update_source_repo or "").strip().strip("/")
    if not repo:
        raise ValueError("update source repo not configured")
    tags_url = f"{GITHUB_API}/repos/{repo}/tags?per_page=1"
    with httpx.Client(timeout=_github_client_timeout()) as client:
        response = client.get(tags_url, headers=_github_headers())
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise ValueError("no tags found on source repo")
    latest = payload[0] or {}
    tag_name = (latest.get("name") or "").strip()
    return {
        "kind": "tag",
        "tag": tag_name,
        "name": tag_name,
        "display": tag_name,
        "url": f"https://github.com/{repo}/tags",
        "publishedAt": "",
        "source": tags_url,
    }


def _has_update(current: dict, latest: dict) -> bool:
    current_version = _normalize_version(current.get("version"))
    latest_version = _normalize_version(latest.get("tag") or latest.get("name"))
    if not latest_version:
        return False
    if current_version in {"", "dev", "unknown", "snapshot"}:
        return True
    return current_version != latest_version


def check_update_payload() -> dict:
    current = runtime_version_payload()
    latest = fetch_latest_release()
    return {
        "current": current,
        "latest": latest,
        "hasUpdate": _has_update(current, latest),
    }


def trigger_update_webhook(user: dict, payload: dict | None = None) -> dict:
    webhook_url = (settings.update_webhook_url or "").strip()
    if not webhook_url:
        raise ValueError("update webhook not configured")

    payload = payload or {}
    now = datetime.now(timezone.utc).isoformat()
    current = runtime_version_payload()
    request_payload = {
        "event": "cloud_mail_update",
        "requestedAt": now,
        "requestedBy": user,
        "target": payload.get("target") or "latest",
        "currentVersion": current.get("version"),
        "currentBuildSha": current.get("buildSha"),
        "sourceRepo": current.get("sourceRepo"),
    }
    headers = {"content-type": "application/json"}
    token = (settings.update_webhook_token or "").strip()
    if token:
        headers["authorization"] = f"Bearer {token}"
        headers["x-update-webhook-token"] = token

    timeout = _github_client_timeout()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(webhook_url, json=request_payload, headers=headers)

    body_text = (response.text or "").strip()
    body = None
    if body_text:
        try:
            body = response.json()
        except Exception:
            body = {"text": body_text[:500]}

    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"webhook failed with status {response.status_code}")

    return {
        "queued": True,
        "statusCode": response.status_code,
        "webhookUrl": webhook_url,
        "response": body,
    }
