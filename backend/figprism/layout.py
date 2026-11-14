"""DocLayout-YOLO ONNX inference on CPU, with two threads and bounded page resolution."""

import ast
from functools import lru_cache
import numpy as np
import onnxruntime as ort
from PIL import Image


@lru_cache(maxsize=1)
def session(path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    model = ort.InferenceSession(
        path, sess_options=options, providers=["CPUExecutionProvider"]
    )
    labels = ast.literal_eval(model.get_modelmeta().custom_metadata_map["names"])
    return model, labels


def predict(image: Image.Image, path: str):
    model, labels = session(path)
    # Centered square letterbox with exact inverse transform for PDF coordinates.
    w, h = image.size
    scale = min(1024 / w, 1024 / h)
    nw, nh = round(w * scale), round(h * scale)
    left, top = (1024 - nw) // 2, (1024 - nh) // 2
    canvas = Image.new("RGB", (1024, 1024), (114, 114, 114))
    canvas.paste(
        image.convert("RGB").resize((nw, nh), Image.Resampling.BILINEAR), (left, top)
    )
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
    predictions = model.run(None, {model.get_inputs()[0].name: tensor})[0].reshape(
        -1, 6
    )
    results = []
    for x0, y0, x1, y1, score, cls in predictions:
        if score < 0.30:
            continue
        box = [
            max(0, float((x0 - left) / scale)),
            max(0, float((y0 - top) / scale)),
            min(w, float((x1 - left) / scale)),
            min(h, float((y1 - top) / scale)),
        ]
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        results.append(
            {"bbox": box, "confidence": float(score), "label": labels[int(cls)]}
        )
    return results
