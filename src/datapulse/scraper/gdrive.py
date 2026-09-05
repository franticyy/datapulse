import re
import requests
from urllib.parse import urlparse, parse_qs
import gdown


def parse_gdrive_url(url: str):
    """
    Google Drive linkinden dosya veya klasör kimliğini (ID) ayıklar.
    Döner: ('file', ID) veya ('folder', ID) veya (None, None)
    """
    if "drive.google.com" not in url:
        return None, None

    # Klasör linki kontrolü (/folders/<ID>)
    folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if folder_match:
        return "folder", folder_match.group(1)

    # Dosya linki kontrolü (/file/d/<ID>)
    file_match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if file_match:
        return "file", file_match.group(1)

    # Query parametresi kontrolü (?id=<ID>)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return "file", qs["id"][0]

    return None, None


def get_gdrive_direct_download_info(file_id: str):
    """
    Büyük dosyalar için Google Drive virüs uyarısını atlatır,
    doğrudan indirme URL'si ve dosya adını döner.
    """
    session = requests.Session()
    base_url = "https://docs.google.com/uc?export=download"
    response = session.get(base_url, params={"id": file_id}, stream=True, timeout=15)

    confirm_token = None
    for k, v in response.cookies.items():
        if k.startswith("download_warning"):
            confirm_token = v
            break

    if not confirm_token:
        match = re.search(r'confirm=([0-9A-Za-z_]+)', response.text)
        if match:
            confirm_token = match.group(1)

    download_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    if confirm_token:
        download_url += f"&confirm={confirm_token}"

    filename = f"gdrive_{file_id}.dat"
    cd = response.headers.get("Content-Disposition", "")
    fname_match = re.search(r'filename="?([^";]+)"?', cd)
    if fname_match:
        filename = fname_match.group(1)

    return download_url, filename


def list_gdrive_folder_files(folder_url: str):
    """
    Herkese açık Google Drive klasöründeki dosyaları tarar ve liste döner.
    """
    try:
        items = gdown.download_folder(
            url=folder_url,
            quiet=True,
            skip_download=True,
            use_cookies=False,
        )

        files = []
        if items:
            for it in items:
                path_str = getattr(it, "path", None) or str(it)
                fname = path_str.replace("\\", "/").split("/")[-1]
                f_id = getattr(it, "id", None)

                stream_url = (
                    f"https://drive.google.com/uc?id={f_id}&export=download"
                    if f_id
                    else None
                )

                files.append(
                    {
                        "filename": fname,
                        "file_id": f_id,
                        "stream_url": stream_url,
                        "local_rel_path": path_str,
                    }
                )
        return files
    except Exception:
        return []