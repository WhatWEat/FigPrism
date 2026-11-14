"""PDF CPU work in short-lived processes: PyMuPDF objects never cross threads.

Request/result pickles are private, exclusively-created internal IPC files; public
uploads are only PDF/TeX bytes and cannot supply an IPC path or a pickle.
"""

import asyncio
import os
from pathlib import Path
import pickle
import sys
import tempfile
from .config import get_settings
from .concurrency import stage


async def cpu_call(operation, pdf_path, **kwargs):
    root = get_settings().data_dir / ".pipeline" / "cpu"
    root.mkdir(parents=True, exist_ok=True)
    async with stage("cpu"):
        with tempfile.TemporaryDirectory(dir=root) as directory:
            request = Path(directory) / "request"
            result = Path(directory) / "result"
            request.write_bytes(
                pickle.dumps(
                    {
                        "operation": operation,
                        "pdf_path": str(pdf_path),
                        "layout_model": get_settings().layout_model,
                        "cpu_threads": get_settings().pipeline.cpu_threads,
                        **kwargs,
                    }
                )
            )
            request.chmod(0o600)
            env = dict(
                os.environ,
                FIGPRISM_PARENT_PID=str(os.getpid()),
                OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
            )
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "figprism.processing",
                str(request),
                str(result),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                _, stderr = await process.communicate()
            except asyncio.CancelledError:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.communicate(), 5)
                    except TimeoutError:
                        process.kill()
                        await process.communicate()
                raise
            if process.returncode or not result.exists():
                raise RuntimeError(f"PDF 计算进程异常退出 ({process.returncode})")
            response = pickle.loads(result.read_bytes())
            if "error" in response:
                raise ValueError(response["error"])
            return response["value"]


def execute(request):
    import pymupdf as fitz
    from .extraction import pdf_title, layout_type, render, Crop, snap
    from .tex import unpack, figures, merge_crops
    import re

    settings = get_settings()
    settings.layout_model = request["layout_model"]
    settings.pipeline.cpu_threads = request["cpu_threads"]
    with fitz.open(request["pdf_path"]) as doc:
        if doc.is_encrypted or not len(doc):
            raise ValueError("PDF 已加密或没有页面")
        if len(doc) > 150:
            raise ValueError("PDF 最多支持 150 页")
        operation = request["operation"]
        if operation == "inspect":
            return {
                "title": pdf_title(doc),
                "layout_type": layout_type(doc),
                "first_page_text": doc[0].get_text(),
            }
        if operation == "plan":
            source_figures = []
            source_path = request.get("source_path")
            if source_path:
                try:
                    source_figures = figures(unpack(Path(source_path).read_bytes()))
                except Exception:
                    pass
            return merge_crops(doc, source_figures)
        if operation == "render":
            return render(doc, request["crop"])
        if operation == "recrop":
            number = request["page"]
            bbox = request["bbox"]
            if not 1 <= number <= len(doc):
                raise ValueError("页码超出范围")
            if (
                len(bbox) != 4
                or not all(0 <= v <= 1 for v in bbox)
                or bbox[0] >= bbox[2]
                or bbox[1] >= bbox[3]
            ):
                raise ValueError("无效裁切坐标")
            page = doc[number - 1]
            absolute = [
                bbox[0] * page.rect.width,
                bbox[1] * page.rect.height,
                bbox[2] * page.rect.width,
                bbox[3] * page.rect.height,
            ]
            crop = Crop(
                number,
                snap(page, absolute) if request["snap"] else absolute,
                request["label"],
                request["caption"],
                1,
            )
            return crop, render(doc, crop)
        if operation == "preview":
            number = request["page"]
            if not 1 <= number <= len(doc):
                raise ValueError("页码超出范围")
            page = doc[number - 1]
            bbox = request["bbox"]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), colorspace=fitz.csRGB)
            return {
                "image": pix.tobytes("png"),
                "count": len(doc),
                "bbox": [
                    bbox[0] / page.rect.width,
                    bbox[1] / page.rect.height,
                    bbox[2] / page.rect.width,
                    bbox[3] / page.rect.height,
                ],
            }
        raise ValueError("Unknown PDF operation")


if __name__ == "__main__":
    # A coordinator crash must not leave native work running after its slot is freed.
    import ctypes, signal

    ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    if os.getppid() != int(os.environ.get("FIGPRISM_PARENT_PID", os.getppid())):
        raise SystemExit(1)
    request = pickle.loads(Path(sys.argv[1]).read_bytes())
    try:
        response = {"value": execute(request)}
    except Exception as exc:
        response = {
            "error": str(exc)[:300]
            if isinstance(exc, ValueError)
            else "PDF 解析或渲染失败"
        }
    Path(sys.argv[2]).write_bytes(pickle.dumps(response))
