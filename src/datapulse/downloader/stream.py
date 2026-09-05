import os
import re
import time
import threading
import gdown
import httpx
from rich.progress import Progress, TaskID


def _get_gdrive_exact_size(file_id: str) -> int:
    """gdown'in URL cozucusu uzerinden Google Drive dosyasinin gercek bayt boyutunu sorgular."""
    try:
        import requests
        session = requests.Session()
        url = f"https://drive.google.com/uc?id={file_id}&export=download"
        res = session.get(url, stream=True, timeout=10)
        
        # Eger Content-Length dogrudan varsa
        cl = res.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > 10000000:
            return int(cl)
            
        # Virüs taraması onayı sayfasındaki gerçek dosya boyutunu HTML'den çek
        # Ornek: (1.63G) veya (1,63 GB) veya (1630000000 bytes)
        size_match = re.search(r'\((\d+[\.,]?\d*)\s*([KMGTP]?B?)\)', res.text, re.IGNORECASE)
        if size_match:
            val_str = size_match.group(1).replace(",", ".")
            unit = size_match.group(2).upper()
            val = float(val_str)
            multipliers = {
                "B": 1, "KB": 1024, "K": 1024,
                "MB": 1024**2, "M": 1024**2,
                "GB": 1024**3, "G": 1024**3
            }
            mult = multipliers.get(unit, 1024**3 if "G" in unit else 1024**2)
            return int(val * mult)
    except Exception:
        pass
    return None


def _download_gdrive_native(
    url_or_id: str,
    destination_file: str,
    progress: Progress = None,
    task_id: TaskID = None,
):
    """Google Drive dosyasini sessizce indirir, gercek boyutu Rich barina yansitir."""
    f_id = url_or_id
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url_or_id) or re.search(
        r"/file/d/([a-zA-Z0-9_-]+)", url_or_id
    )
    if match:
        f_id = match.group(1)

    dest_dir = os.path.dirname(os.path.abspath(destination_file))
    base_name = os.path.basename(destination_file)

    # Eski part dosyalarini temizle
    if os.path.exists(dest_dir):
        for p in os.listdir(dest_dir):
            if p.startswith(base_name) and p.endswith(".part"):
                try:
                    os.remove(os.path.join(dest_dir, p))
                except OSError:
                    pass

    # Gercek boyutu sorgula
    exact_size = None
    if f_id:
        exact_size = _get_gdrive_exact_size(f_id)

    if progress and task_id is not None:
        if exact_size:
            progress.update(task_id, total=exact_size, completed=0)
        else:
            progress.update(task_id, total=None, completed=0)

    stop_monitor = threading.Event()

    def _monitor():
        last_size = 0
        while not stop_monitor.is_set():
            time.sleep(0.5)
            current_size = 0
            if os.path.exists(destination_file):
                current_size = os.path.getsize(destination_file)
            elif os.path.exists(dest_dir):
                for p in os.listdir(dest_dir):
                    if p.startswith(base_name) and p.endswith(".part"):
                        try:
                            current_size = os.path.getsize(os.path.join(dest_dir, p))
                        except OSError:
                            pass
                        break

            if current_size > last_size and progress and task_id is not None:
                progress.update(task_id, completed=current_size)
                last_size = current_size

    t = threading.Thread(target=_monitor, daemon=True)
    t.start()

    try:
        gdown.download(id=f_id, output=destination_file, quiet=True, resume=True)
    finally:
        stop_monitor.set()
        t.join(timeout=1.0)

    if os.path.exists(destination_file):
        actual_size = os.path.getsize(destination_file)
        if progress and task_id is not None:
            progress.update(task_id, total=actual_size, completed=actual_size)

    return destination_file


def download_stream(
    url: str,
    destination_file: str,
    chunk_size: int = 1048576,
    progress: Progress = None,
    task_id: TaskID = None,
) -> str:
    """Genomik veri akis motoru (Nextcloud, S3, ENA, Google Drive)."""
    dest_dir = os.path.dirname(os.path.abspath(destination_file))
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    # 1. Google Drive Akisi
    if "drive.google.com" in url or "export=download" in url or "uc?id=" in url:
        return _download_gdrive_native(
            url, destination_file, progress=progress, task_id=task_id
        )

    # 2. Standart HTTP / S3 / WebDAV Akisi (NCBI, ENA, Nextcloud)
    headers = {}
    downloaded_bytes = 0
    file_mode = "wb"

    if os.path.exists(destination_file):
        downloaded_bytes = os.path.getsize(destination_file)
        if downloaded_bytes > 0:
            headers["Range"] = f"bytes={downloaded_bytes}-"
            file_mode = "ab"

    client = httpx.Client(follow_redirects=True, timeout=120.0)

    try:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:
                if progress and task_id is not None:
                    progress.update(
                        task_id,
                        completed=downloaded_bytes,
                        total=downloaded_bytes,
                    )
                return destination_file

            response.raise_for_status()

            total_size = response.headers.get("Content-Length")
            total_bytes = (
                int(total_size) + downloaded_bytes if total_size else None
            )

            if progress and task_id is not None and total_bytes:
                progress.update(
                    task_id, total=total_bytes, completed=downloaded_bytes
                )

            with open(destination_file, file_mode) as target_out:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        target_out.write(chunk)
                        if progress and task_id is not None:
                            progress.update(task_id, advance=len(chunk))
                target_out.flush()
                try:
                    os.fsync(target_out.fileno())
                except OSError:
                    pass
    finally:
        client.close()

    return destination_file