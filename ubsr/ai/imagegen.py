"""Optional image generation through a Stable Diffusion WebUI (AUTOMATIC1111-style) API."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

NEGATIVE = "blurry, deformed, lowres, text, watermark, extra fingers, bad anatomy"


def generate_image(base_url: str, prompt: str, out_path: Path | str, steps: int = 20, width: int = 768,
                   height: int = 768, timeout: float = 600.0, negative: str = NEGATIVE) -> Optional[str]:
    """Render ``prompt`` to ``out_path``. Returns the path, or None on any failure."""
    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "steps": int(steps),
        "width": width,
        "height": height,
        "sampler_name": "DPM++ 2M",
        "cfg_scale": 6.5,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/sdapi/v1/txt2img",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        images = body.get("images") or []
        if not images:
            return None
        data = images[0]
        if "," in data[:40]:
            data = data.split(",", 1)[1]
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(data))
        return str(out_path)
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
