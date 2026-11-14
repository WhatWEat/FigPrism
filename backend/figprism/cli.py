import asyncio
import json
import os
from pathlib import Path
import typer
from .db import init_db, connect
from .auth import create_user
from .config import get_settings
from .ingest import (
    ingest_pdf,
    resolve,
    recrop as do_recrop,
    rebuild,
    new_job,
    update_job,
)
from .network import fetch
from .sources import sync as do_sync

app = typer.Typer(help="FigPrism research figure pipeline")
auth = typer.Typer()
queue = typer.Typer()
app.add_typer(auth, name="auth")
app.add_typer(queue, name="queue")


@app.callback()
def setup():
    init_db()


@auth.command("create-admin")
def create_admin(
    username: str = "admin",
    password: str = typer.Option(
        None, envvar="FIGPRISM_ADMIN_PASSWORD", hide_input=True, prompt=True
    ),
):
    create_user(username, password, "admin")
    typer.echo(f"Administrator {username} created")


@app.command()
def ingest(
    input: str = typer.Option(None, "--input"),
    pdf: Path = typer.Option(None, "--pdf"),
    domains: str = "",
    venue: str = "Preprint",
    force_include: bool = True,
    vision_driver: str | None = None,
):
    async def run():
        meta = {"venue": venue}
        if domains:
            meta["domains"] = domains.split(",")
        if pdf:
            data = pdf.read_bytes()
        elif input:
            url, resolved = await resolve(input)
            resolved.update(meta)
            meta = resolved
            data = await fetch(url)
        else:
            raise typer.BadParameter("Pass --input or --pdf")
        typer.echo(await ingest_pdf(data, meta, vision_driver=vision_driver))

    asyncio.run(run())


@app.command()
def sync(
    source: str = "all",
    days: int = 3,
    vision_driver: str | None = None,
    limit: int = 50,
):
    jid = new_job(None, "sync", {"source": source, "days": days})
    try:
        typer.echo(
            json.dumps(
                asyncio.run(
                    do_sync(
                        source=source,
                        days=days,
                        limit=limit,
                        vision_driver=vision_driver,
                        job_id=jid,
                    )
                ),
                ensure_ascii=False,
            )
        )
    except Exception:
        update_job(jid, 0, "同步任务异常退出，请检查远端连接", "failed")
        raise


@app.command()
def backfill(
    years: str = "2025,2026",
    domains: str = "all",
    limit_per_domain: int = 50,
    vision_driver: str | None = None,
):
    typer.echo(
        json.dumps(
            asyncio.run(
                do_sync(
                    backfill=True,
                    years=tuple(map(int, years.split(","))),
                    domain=domains,
                    limit=limit_per_domain,
                    vision_driver=vision_driver,
                )
            ),
            ensure_ascii=False,
        )
    )


@queue.command("list")
def list_queue(
    type: str = "review_or_repair", json_output: bool = typer.Option(False, "--json")
):
    with connect() as db:
        rows = db.execute(
            "SELECT f.id,f.paper_id,f.fig_label,f.page_number,f.bbox,f.caption,f.review_status,p.title FROM figures f JOIN papers p ON p.id=f.paper_id WHERE f.review_status='needs_review' OR EXISTS (SELECT 1 FROM repair_queue r WHERE r.figure_id=f.id AND r.status='pending')"
        ).fetchall()
    typer.echo(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))


@app.command()
def recrop(figure_id: str, page: int, bbox: str, snap_vector: bool = True):
    asyncio.run(
        do_recrop(figure_id, page, list(map(float, bbox.split(","))), snap_vector)
    )
    typer.echo("Recrop saved and metadata backed up")


@app.command("rebuild-from-webdav")
def rebuild_from_webdav():
    typer.echo(f"Restored {asyncio.run(rebuild())} figures")


if __name__ == "__main__":
    app()
