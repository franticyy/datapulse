from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from datapulse.downloader.mirror import resolve_optimal_mirror


def download_stream(
    url: str,
    output_dir: str = "downloads",
    filename: Optional[str] = None,
    chunk_size: int = 1024 * 1024,
) -> Path:
    """Streams and downloads a file with HTTP Range auto-resume and cloud mirror resolution.

    Args:
        url: Source download URL.
        output_dir: Target local directory.
        filename: Custom destination filename. If None, derived from URL.
        chunk_size: Stream buffer size in bytes (default: 1 MB).

    Returns:
        Path: Path object pointing to the downloaded artifact.
    """
    # 1. Resolve optimal cloud mirror (e.g. AWS Open Data fallback)
    resolved_url, provider = resolve_optimal_mirror(url)
    if provider != "Direct Origin":
        print(f"[*] Optimal mirror resolved: {provider}")
    active_url = resolved_url

    # 2. Destination path resolution
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        parsed_path = urlparse(active_url).path
        filename = Path(parsed_path).name or "downloaded_artifact"

    destination_file = target_dir / filename

    # 3. Check existing bytes for HTTP Range recovery
    existing_bytes = destination_file.stat().st_size if destination_file.exists() else 0
    headers = {}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        with client.stream("GET", active_url, headers=headers) as response:
            # Server responded with Range Not Satisfiable (file already fully downloaded)
            if response.status_code == 416:
                return destination_file

            response.raise_for_status()

            # Determine total file size
            content_range = response.headers.get("Content-Range")
            if content_range and "/" in content_range:
                total_size = int(content_range.split("/")[-1])
            else:
                content_length = response.headers.get("Content-Length")
                total_size = (
                    int(content_length) + existing_bytes
                    if content_length
                    else None
                )

            # File mode: append if resuming (206), write new if fresh (200)
            file_mode = "ab" if response.status_code == 206 else "wb"
            if response.status_code != 206:
                existing_bytes = 0

            progress = Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            )

            with progress:
                task_id = progress.add_task(
                    f"Fetching {filename}",
                    total=total_size,
                    completed=existing_bytes,
                )

                with open(destination_file, file_mode) as target_out:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        if chunk:
                            target_out.write(chunk)
                            progress.update(task_id, advance=len(chunk))

    return destination_file