"""Reproducible scheduling benchmark using injected I/O latency; no external calls.

This measures overlap/backpressure, not real provider bandwidth or model speed.
"""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from figprism.config import get_settings
from figprism.db import init_db, connect
from figprism.concurrency import stage, bounded_map
from figprism.extraction import Crop
from figprism.ingest import ingest_pdf
from figprism.vision import Verdict


async def cpu(operation, path, **kwargs):
    async with stage("cpu"):
        await asyncio.sleep(0.04)
        if operation == "inspect":
            return {
                "title": "Benchmark",
                "layout_type": "single",
                "first_page_text": "",
            }
        if operation == "plan":
            return [
                Crop(1, [0, 0, 400, 100], f"Fig. {i}", "benchmark", 0.9)
                for i in range(6)
            ]
        return {
            "hd": kwargs["crop"].label.encode(),
            "thumb": b"thumb",
            "raw": b"%PDF-raw",
            "width": 400,
            "height": 100,
            "aspect_ratio": 4,
            "blurhash": None,
            "fonts": [],
            "subitems": [],
            "palette": {"colors": [], "pairs": [], "neutrals": [], "buckets": []},
        }


async def judge(*args):
    async with stage("vision"):
        await asyncio.sleep(0.08)
        return Verdict(
            archetype="Pipeline",
            crop_ok=True,
            confidence=0.9,
            sub_tags=[],
            reason="simulated",
        )


async def upload(*args, **kwargs):
    async with stage("upload"):
        await asyncio.sleep(0.08)


async def scenario(serial):
    with tempfile.TemporaryDirectory() as directory:
        with patch.dict(
            os.environ,
            {
                "FIGPRISM_DATA_DIR": directory,
                "FIGPRISM_CONFIG": directory + "/absent.yaml",
                "FIGPRISM_SECRET_KEY": "benchmark-" * 5,
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()
            settings.layout_model = None
            if serial:
                settings.pipeline.papers = 1
                settings.pipeline.cpu = 1
                settings.pipeline.vision = 1
                settings.pipeline.per_paper_figures = 1
            init_db()
            with (
                patch("figprism.ingest.cpu_call", cpu),
                patch("figprism.ingest.judge", judge),
                patch("figprism.storage.Storage.put", upload),
            ):
                start = time.perf_counter()
                await bounded_map(
                    lambda i: ingest_pdf(f"%PDF benchmark-{i}".encode()), range(3), 3
                )
                elapsed = time.perf_counter() - start
            with connect() as db:
                count = db.execute("SELECT COUNT(*) FROM figures").fetchone()[0]
            return {"seconds": round(elapsed, 3), "papers": 3, "figures": count}


async def main():
    serial = await scenario(True)
    parallel = await scenario(False)
    print(
        json.dumps(
            {
                "kind": "injected latency; not production throughput",
                "serial": serial,
                "staged": parallel,
                "speedup": round(serial["seconds"] / parallel["seconds"], 2),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
