"""Ingest a small, real-paper starter set. No synthetic figures or invented venue badges."""

import asyncio
import argparse
from figprism.db import init_db, connect
from figprism.ingest import resolve, ingest_pdf, new_job, update_job
from figprism.network import fetch
from figprism.sources import verified


async def main(papers):
    init_db()
    for aid in papers:
        with connect() as db:
            if db.execute(
                "SELECT id FROM papers WHERE arxiv_id=? AND ingest_status='completed'",
                (aid,),
            ).fetchone():
                continue
        jid = new_job(None, "bootstrap", {"input": aid})
        try:
            print("Starting", aid, flush=True)
            url, meta = await resolve(aid)
            checked = await verified(dict(meta))
            if checked:
                meta = checked
            data = await fetch(url)
            pid = await ingest_pdf(data, meta, job_id=jid)
            print("Completed", aid, pid, flush=True)
        except Exception as e:
            update_job(jid, 0, "Starter paper failed; retry from CLI", "failed")
            print("Failed", aid, type(e).__name__, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--papers", nargs="+", default=["2501.00663", "2502.09992", "2505.03335"]
    )
    asyncio.run(main(parser.parse_args().papers))
