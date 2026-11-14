"""Retire only the recorded old FigPrism containers once accepted work is idle."""

import json
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
state = ROOT / "data" / "rollout" / "legacy.json"
if not state.exists():
    raise SystemExit(0)
record = json.loads(state.read_text())
with sqlite3.connect(ROOT / "data" / "figprism.db", timeout=5) as db:
    active = db.execute(
        "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"
    ).fetchone()[0]
if active:
    print(f"Preserving legacy runtime: {active} accepted jobs still active.")
    raise SystemExit(0)
for name, expected in record["containers"].items():
    info = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}} {{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    if info.returncode:
        continue
    actual, running = info.stdout.strip().split()
    if actual != expected:
        raise SystemExit("Container identity changed; automatic retirement stopped.")
    if running == "true":
        processes = subprocess.check_output(
            ["docker", "top", name, "-eo", "args"], text=True
        ).splitlines()[1:]
        # An attached CLI may still be preparing a job that has not been written to SQLite.
        if "backend" in name and any(
            "uvicorn figprism.main:app" not in row for row in processes
        ):
            print("Preserving legacy runtime: attached process still running.")
            raise SystemExit(0)
for name in record["containers"]:
    subprocess.run(["docker", "stop", "--time", "30", name], check=False)
(ROOT / "data" / ".pipeline" / "recovery-exempt.json").unlink(missing_ok=True)
state.rename(state.with_suffix(".completed.json"))
subprocess.run(
    ["systemctl", "disable", "--now", "figprism-drain-legacy.timer"], check=True
)
print("Legacy containers stopped; database and assets preserved.")
