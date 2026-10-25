"""Connect the local Python worker to the Convex deployment used by apps/web.

Reads the deployment URL from apps/web/.env.local, keeps or creates a worker secret
in the root .env, and sets the same secret as WORKER_SECRET on the deployment from a
temporary file that is deleted right after. The secret is never printed.

Run from the repository root after `npx convex dev` has provisioned a deployment:
    services/api/.venv/Scripts/python scripts/convex_setup.py
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = ROOT / ".env"
WEB = ROOT / "apps" / "web"
WEB_ENV = WEB / ".env.local"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.split("#", 1)[0].strip().strip('"')
    return values


def upsert(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    for index, line in enumerate(lines):
        name = line.split("=", 1)[0].strip()
        if name in updates:
            lines[index] = f"{name}={updates[name]}"
            done.add(name)
    lines.extend(f"{name}={value}" for name, value in updates.items() if name not in done)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    url = read_env(WEB_ENV).get("NEXT_PUBLIC_CONVEX_URL", "")
    if not url:
        print("apps/web/.env.local has no NEXT_PUBLIC_CONVEX_URL. Run `npx convex dev` in apps/web first.")
        return 1
    secret = read_env(ROOT_ENV).get("CONVEX_WORKER_SECRET") or secrets.token_urlsafe(32)
    upsert(ROOT_ENV, {"CONVEX_URL": url, "CONVEX_WORKER_SECRET": secret})
    handle, temp_name = tempfile.mkstemp(suffix=".env")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temp:
            temp.write(f"WORKER_SECRET={secret}\n")
        result = subprocess.run(
            f'npx convex env set --force --from-file "{temp_name}"',
            cwd=WEB,
            text=True,
            shell=True,
            capture_output=True,
        )
    finally:
        os.remove(temp_name)
    if result.returncode != 0:
        print("Setting WORKER_SECRET on the deployment failed:")
        print(result.stderr.replace(secret, "[redacted]")[-800:])
        return 1
    print(f"Worker connected to {url}. CONVEX_URL and CONVEX_WORKER_SECRET are in .env; WORKER_SECRET is set on the deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
