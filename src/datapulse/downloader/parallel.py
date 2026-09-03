from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from datapulse.validator.archive import verify_archive_integrity

CHUNK_SIZE = 1024 * 1024  # 1 MB


def _download_worker(
    item: Dict[str, Any],
    output_dir: Path,
    progress: Progress,
    task_id: int,
    calculate_hash_func: Callable,
) -> Dict[str, Any]:
    url = item["url"]
    expected_md5 = item.get("expected_md5", "")
    filename = url.split("/")[-1].split("?")[0] or "data.bin"
    destination = output_dir / filename

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Encoding": "identity",
    }

    downloaded_bytes = 0
    mode = "wb"
    if destination.exists():
        downloaded_bytes = destination.stat().st_size
        headers["Range"] = f"bytes={downloaded_bytes}-"
        mode = "ab"

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)

    try:
        with httpx.Client(
            timeout=httpx.Timeout(120.0, connect=20.0),
            limits=limits,
            follow_redirects=True,
            headers=headers,
            http2=True,
        ) as client:
            with client.stream("GET", url) as response:
                if response.status_code == 416:
                    total_bytes = downloaded_bytes
                elif response.status_code in (200, 206):
                    content_length = response.headers.get("content-length")
                    total_bytes = int(content_length) + downloaded_bytes if content_length else None
                else:
                    response.raise_for_status()
                    total_bytes = None

                progress.update(task_id, total=total_bytes, completed=downloaded_bytes)
                progress.start_task(task_id)

                if response.status_code != 416:
                    with open(destination, mode, buffering=CHUNK_SIZE) as f:
                        for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                progress.update(task_id, advance=len(chunk))

        # 1. Kriptografik Hash Hesaplama & Denetimi
        current_hash = calculate_hash_func(destination, algorithm="md5" if expected_md5 else "sha256")
        hash_verified = True
        if expected_md5:
            hash_verified = current_hash.lower() == expected_md5.lower()

        # 2. Arşiv İç Bütünlük (CRC / Gzip / Tar) Denetimi
        archive_ok, archive_msg = verify_archive_integrity(destination)

        is_fully_valid = hash_verified and archive_ok

        if not is_fully_valid:
            # Bozuksa dosyayı diskten temizle
            destination.unlink(missing_ok=True)

        return {
            "success": is_fully_valid,
            "filename": destination.name,
            "size_bytes": destination.stat().st_size if destination.exists() else 0,
            "source_url": url,
            "calculated_md5": current_hash if expected_md5 else "",
            "calculated_sha256": current_hash if not expected_md5 else "",
            "verified": is_fully_valid,
            "archive_status": archive_msg,
            "error": None if is_fully_valid else f"Hash: {hash_verified}, Arşiv: {archive_msg}",
        }

    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "size_bytes": 0,
            "source_url": url,
            "calculated_md5": "",
            "calculated_sha256": "",
            "verified": False,
            "archive_status": "Hata",
            "error": str(e),
        }


def download_concurrently(
    items: List[Dict[str, Any]],
    output_dir: str = "downloads",
    max_workers: int = 3,
    calculate_hash_func: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.fields[filename]}"),
        BarColumn(bar_width=25),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        refresh_per_second=4,
    )

    results = []

    with progress:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {}

            for item in items:
                fname = item["url"].split("/")[-1].split("?")[0]
                task_id = progress.add_task("download", filename=fname[:25], start=False)
                future = executor.submit(
                    _download_worker,
                    item=item,
                    output_dir=out_dir,
                    progress=progress,
                    task_id=task_id,
                    calculate_hash_func=calculate_hash_func,
                )
                future_to_item[future] = task_id

            for future in as_completed(future_to_item):
                res = future.result()
                results.append(res)

    return results