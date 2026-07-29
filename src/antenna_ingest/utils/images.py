from __future__ import annotations

import base64
from pathlib import Path


def image_file_to_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
