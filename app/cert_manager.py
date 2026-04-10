from __future__ import annotations

import json
import platform
import subprocess

from app.config import settings
from app.time_utils import utcnow


def run_certbot_script(action: str, *, domain: str, email: str) -> dict:
    if platform.system().lower().startswith("win"):
        return {"ok": False, "message": "certbot scripts require linux host"}

    scripts_dir = settings.certbot_scripts_path
    script_map = {
        "issue": scripts_dir / "issue-cert.sh",
        "renew": scripts_dir / "renew-cert.sh",
    }
    script = script_map[action]
    if not script.exists():
        return {"ok": False, "message": f"script not found: {script}"}

    settings.certbot_webroot_path.mkdir(parents=True, exist_ok=True)
    command = [
        str(script),
        domain,
        email,
        str(settings.certbot_webroot_path),
        settings.certbot_reload_command,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    if completed.returncode != 0:
        return {"ok": False, "message": error or output or f"{action} failed", "returncode": completed.returncode}
    return {"ok": True, "message": output or f"{action} success"}


def cert_status_payload(current: dict) -> dict:
    return {
        "domain": current.get("certDomain", ""),
        "email": current.get("certEmail", ""),
        "autoRenew": current.get("certAutoRenew", 0),
        "status": current.get("certStatus", "idle"),
        "lastResult": current.get("certLastResult", ""),
        "lastRunAt": current.get("certLastRunAt", ""),
        "webroot": str(settings.certbot_webroot_path),
        "reloadCommand": settings.certbot_reload_command,
    }


def apply_cert_update(current: dict, result: dict) -> dict:
    return {
        **current,
        "certStatus": "ok" if result.get("ok") else "error",
        "certLastResult": result.get("message", ""),
        "certLastRunAt": utcnow().isoformat(),
    }
