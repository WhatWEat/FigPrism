"""Hourly, project-scoped health checks and recoverable production repairs."""

import datetime
import json
import os
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "ops" / "hourly-maintenance.json"
actions = []
problems = []


def run(*args, timeout=60):
    return subprocess.run(
        args, check=False, cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )


def log(action):
    actions.append(action)
    print(action, flush=True)


def inspect(name):
    r = run("docker", "inspect", name)
    return json.loads(r.stdout)[0] if r.returncode == 0 else None


def compose(*args):
    r = run("docker", "compose", *args, timeout=120)
    if r.returncode:
        problems.append("Compose 操作失败：" + " ".join(args))
    return r


def main():
    # Exact container names prevent touching other applications on this host.
    for service in ("backend", "uploader", "frontend"):
        name = f"figprism-v2-{service}-1"
        state = inspect(name)
        if not state or not state["State"]["Running"]:
            compose("up", "-d", "--no-deps", service)
            log("恢复服务：" + service)
        elif state["State"].get("Health", {}).get("Status") == "unhealthy":
            compose("restart", service)
            log("重启不健康服务：" + service)
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8101/api/health", timeout=10
        ) as r:
            if r.status != 200:
                problems.append("本地 API 健康检查失败")
    except OSError:
        problems.append("本地 API 暂不可用，检查恢复服务日志")
    repair = run(
        "docker",
        "compose",
        "exec",
        "-T",
        "uploader",
        "figprism",
        "storage",
        "maintain",
        timeout=120,
    )
    if repair.returncode:
        problems.append("资产巡检未能执行")
    else:
        report = json.loads(repair.stdout)
        for item in report["repaired_names"]:
            log("修复远端不支持的子图文件名：" + item["old"])
        problems.extend(report["warnings"])
    live = [
        json.loads(line)
        for line in run("docker", "ps", "--format", "{{json .}}").stdout.splitlines()
        if line.strip()
    ]
    live_ids = {r["ID"] for r in live}
    live_names = {r["Names"] for r in live}
    with sqlite3.connect(ROOT / "data/figprism.db", timeout=30) as db:
        db.row_factory = sqlite3.Row
        # New CLI jobs record their owning independent container. Recover only
        # explicit owners; do not guess about user-submitted API jobs.
        for job in db.execute(
            "SELECT id,payload FROM jobs WHERE user_id IS NULL AND status IN ('queued','running')"
        ):
            owner = json.loads(job["payload"]).get("worker_owner")
            if owner and not any(
                x.startswith(owner) or owner.startswith(x) for x in live_ids
            ):
                db.execute(
                    "UPDATE jobs SET status='failed',message='巡检发现所属进程已退出，已安排恢复',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (job["id"],),
                )
                log("修正失去进程的任务：" + job["id"])
        domains = [
            r[0] for r in db.execute("SELECT slug FROM domains WHERE is_active=1")
        ]
        coverage = dict(
            db.execute(
                "SELECT j.value,count(DISTINCT p.id) FROM papers p,json_each(p.domains) j WHERE p.venue_year=2026 AND p.ingest_status='completed' GROUP BY j.value"
            )
        )
        cvpr = db.execute(
            "SELECT count(*) FROM papers WHERE venue='CVPR' AND venue_year=2026 AND ingest_status='completed'"
        ).fetchone()[0]
        missing = [d for d in domains if coverage.get(d, 0) < 5]
        jobs = [
            dict(r)
            for r in db.execute(
                "SELECT id,message,updated_at FROM jobs WHERE status IN ('queued','running') AND kind='backfill'"
            )
        ]
    coldstart = inspect("figprism-v2-coldstart-1")
    running = bool(coldstart and coldstart["State"]["Running"])
    seed_running = "figprism-cvpr-2026" in live_names
    extra_batch = None
    extra_batches = []
    for suffix, target in (("100", 100), ("50", 50)):
        pointer = ROOT / ("data/ops/extra_" + suffix + "_active.json")
        if not pointer.exists():
            continue
        state_path = Path(json.loads(pointer.read_text())["state_file"])
        if state_path.exists():
            state = json.loads(state_path.read_text())
            batch = {
                "target": target,
                "completed": len(state.get("completed_ids", [])),
                "job_id": state.get("job_id"),
            }
        else:
            batch = {"target": target, "completed": 0}
        extra_batches.append(batch)
        extra_batch = batch
        if batch["completed"] < batch["target"]:
            seed_running = True
            if "figprism-extra-" + suffix not in live_names:
                resumed = run(
                    "systemctl",
                    "start",
                    "--no-block",
                    "figprism-extra-" + suffix + ".service",
                )
                if resumed.returncode:
                    problems.append("新增 " + suffix + " 篇批次恢复失败")
                else:
                    log("恢复新增 " + suffix + " 篇独立批次")
    if (missing or cvpr < 5) and not running and not seed_running:
        compose("--profile", "maintenance", "up", "-d", "--no-deps", "coldstart")
        log("恢复独立冷启动任务")
    elif running:
        # Restart only a proven stalled container-owned job; completed/no-work
        # states are not treated as failures.
        owner = coldstart["Id"][:12]
        with sqlite3.connect(ROOT / "data/figprism.db", timeout=30) as db:
            stale = db.execute(
                "SELECT id FROM jobs WHERE json_extract(payload,'$.worker_owner')=? AND status='running' AND updated_at<datetime('now','-45 minutes')",
                (owner,),
            ).fetchall()
        if stale:
            compose("--profile", "maintenance", "restart", "coldstart")
            log("重启超过 45 分钟没有进度的独立冷启动任务")
    result = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),  # noqa: UP017 (host Python 3.8)
        "actions": actions,
        "problems": problems,
        "coverage": coverage,
        "cvpr2026": cvpr,
        "domains_below_five": missing,
        "jobs": jobs,
        "extra_batch": extra_batch,
        "extra_batches": extra_batches,
        "storage": report.get("storage", {}) if repair.returncode == 0 else {},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    os.replace(temp, REPORT)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
