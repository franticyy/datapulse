import logging
import os
import requests

logger = logging.getLogger(__name__)


def download_stream(
    url: str,
    destination_file: str,
    progress=None,
    task_id=None,
    chunk_size: int = 1024 * 1024,
) -> str:
    headers = {}
    existing_size = 0

    if os.path.exists(destination_file):
        existing_size = os.path.getsize(destination_file)

    mode = "wb"
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        mode = "ab"

    resp = requests.get(url, headers=headers, stream=True, timeout=(30, None))
    resp.raise_for_status()

    if resp.status_code == 416:
        logger.debug("HTTP 416: %s zaten tam, atlanıyor.", os.path.basename(destination_file))
        return destination_file

    if resp.status_code == 206:
        content_len = int(resp.headers.get("content-length", 0))
        full_total = existing_size + content_len
    else:
        existing_size = 0
        mode = "wb"
        full_total = int(resp.headers.get("content-length", 0)) or None

    if progress and task_id is not None:
        progress.update(task_id, total=full_total, completed=existing_size)

    with open(destination_file, mode) as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                if progress and task_id is not None:
                    progress.update(task_id, advance=len(chunk))

    return destination_file