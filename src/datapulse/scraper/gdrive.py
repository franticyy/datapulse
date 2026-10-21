import logging
import re
from urllib.parse import urlparse, parse_qs

import gdown

logger = logging.getLogger(__name__)


def parse_gdrive_url(url: str):
    if "drive.google.com" not in url:
        return None, None

    folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if folder_match:
        return "folder", folder_match.group(1)

    file_match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if file_match:
        return "file", file_match.group(1)

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return "file", qs["id"][0]

    return None, None


def get_gdrive_direct_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?id={file_id}&export=download"


def list_gdrive_folder_files(folder_url: str) -> list:
    try:
        items = gdown.download_folder(
            url=folder_url,
            quiet=True,
            skip_download=True,
            use_cookies=False,
        )
    except Exception as e:
        logger.warning("Google Drive klasörü taranamadı: %s — %s", folder_url, e)
        return []

    if not items:
        logger.warning("Google Drive klasöründe dosya bulunamadı: %s", folder_url)
        return []

    files = []
    for it in items:
        path_str = getattr(it, "path", None) or str(it)
        fname = path_str.replace("\\", "/").split("/")[-1]
        f_id = getattr(it, "id", None)
        stream_url = get_gdrive_direct_download_url(f_id) if f_id else None

        files.append({
            "filename": fname,
            "name": fname,
            "file_id": f_id,
            "stream_url": stream_url,
            "url": stream_url,
        })

    logger.info("Google Drive: %d dosya bulundu.", len(files))
    return files


def download_gdrive_file(file_id: str, destination: str) -> str:
    url = get_gdrive_direct_download_url(file_id)
    result = gdown.download(url=url, output=destination, quiet=False)
    if not result:
        raise RuntimeError(f"Google Drive dosyası indirilemedi: {file_id}")
    return result