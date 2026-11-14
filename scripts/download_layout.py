"""Download the pinned DocLayout-YOLO ONNX artifact; no executable model code is loaded."""

import hashlib
from pathlib import Path
import httpx

REVISION = "ee7c3d744e5c47c58e267044ac825f95abe69653"
URL = f"https://huggingface.co/wybxc/DocLayout-YOLO-DocStructBench-onnx/resolve/{REVISION}/doclayout_yolo_docstructbench_imgsz1024.onnx"
if __name__ == "__main__":
    path = Path("data/models/doclayout.onnx")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".download")
    with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with temp.open("wb") as file:
            for data in response.iter_bytes():
                file.write(data)
    expected = "fece9af02f618b603ff7921ccec6861d13e7e1f9830e091dfb7e8ad9311e5b21"
    if hashlib.sha256(temp.read_bytes()).hexdigest() != expected:
        temp.unlink()
        raise RuntimeError("Layout model checksum mismatch")
    temp.replace(path)
    print(
        f"Downloaded {path} ({path.stat().st_size} bytes); sha256={hashlib.sha256(path.read_bytes()).hexdigest()}"
    )
