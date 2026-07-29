from __future__ import annotations

import base64

from antenna_ingest.utils.images import image_file_to_data_url


def test_image_file_to_data_url_encodes_png_bytes(tmp_path) -> None:
    image_path = tmp_path / "page.png"
    image_bytes = b"\x89PNG\r\n\x1a\n"
    image_path.write_bytes(image_bytes)

    result = image_file_to_data_url(image_path)

    assert result == (
        "data:image/png;base64,"
        + base64.b64encode(image_bytes).decode("ascii")
    )
