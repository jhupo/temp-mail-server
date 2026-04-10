from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings
from app.time_utils import utcnow


def _run(command: list[str] | str, *, cwd: Path, shell: bool = False) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=shell,
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
    return completed.returncode, output


def update_status() -> dict:
    repo = settings.repo_root_path
    branch = settings.update_branch
    remote = settings.update_remote
    local_code, local_out = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    remote_code, remote_out = _run(["git", "ls-remote", remote, f"refs/heads/{branch}"], cwd=repo)
    local_head = local_out.splitlines()[-1] if local_code == 0 and local_out else ""
    remote_head = ""
    if remote_code == 0 and remote_out:
        remote_head = remote_out.split()[0]
    return {
        "branch": branch,
        "remote": remote,
        "localHead": local_head,
        "remoteHead": remote_head,
        "hasUpdate": bool(local_head and remote_head and local_head != remote_head),
        "checkedAt": utcnow().isoformat(),
        "message": remote_out if remote_code != 0 else "ok",
    }


def apply_update() -> dict:
    repo = settings.repo_root_path
    branch = settings.update_branch
    remote = settings.update_remote
    steps: list[dict] = []

    commands: list[tuple[str, list[str] | str, bool, Path]] = [
        ("git_pull", ["git", "pull", "--ff-only", remote, branch], False, repo),
        ("pip_install", [settings.python_executable, "-m", "pip", "install", "-r", "requirements.txt"], False, repo),
        ("frontend_install", ["npm", "install", "--legacy-peer-deps"], False, repo / "frontend"),
        ("frontend_build", ["npm", "run", "build"], False, repo / "frontend"),
        ("alembic_upgrade", ["alembic", "upgrade", "head"], False, repo),
    ]

    reload_command = settings.update_reload_command.strip()
    if reload_command:
        commands.append(("reload", reload_command, True, repo))

    for name, command, shell, cwd in commands:
        code, output = _run(command, cwd=cwd, shell=shell)
        steps.append({"step": name, "code": code, "output": output})
        if code != 0:
            return {
                "ok": False,
                "steps": steps,
                "message": f"{name} failed",
                "finishedAt": utcnow().isoformat(),
            }

    return {
        "ok": True,
        "steps": steps,
        "message": "update applied",
        "finishedAt": utcnow().isoformat(),
    }
