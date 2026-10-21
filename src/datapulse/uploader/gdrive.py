import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# .env dosyasını otomatik yükle (varsa)
load_dotenv()

# Ortam değişkenlerinden oku
CLIENT_ID = os.getenv("GDRIVE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GDRIVE_CLIENT_SECRET", "")

# Sadece DataPulse uygulamasının yüklediği dosyaları yönetme kapsamı
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def extract_folder_id(folder_input: str) -> str:
    if not folder_input or not folder_input.strip():
        return None
    val = folder_input.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", val)
    if match:
        return match.group(1)
    return val


def get_gdrive_service():
    creds = None
    token_path = os.path.expanduser("~/.datapulse_gdrive_token.json")

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not CLIENT_ID or not CLIENT_SECRET:
                raise RuntimeError(
                    "Google Drive credentials eksik. "
                    "GDRIVE_CLIENT_ID ve GDRIVE_CLIENT_SECRET ortam değişkenlerini "
                    "veya .env dosyasını tanımla."
                )
            client_config = {
                "installed": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)

        try:
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
        except OSError:
            pass

    return build("drive", "v3", credentials=creds)


def upload_gdrive(
    file_path: str,
    folder_id: str = None,
    progress=None,
    task_id=None,
    max_retries: int = 5,
    **_kwargs,
):
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")

    clean_folder_id = extract_folder_id(folder_id)
    service = get_gdrive_service()
    file_name = path.name
    file_size = path.stat().st_size

    file_metadata = {"name": file_name}
    if clean_folder_id:
        file_metadata["parents"] = [clean_folder_id]

    media = MediaFileUpload(
        str(path),
        resumable=True,
        chunksize=5 * 1024 * 1024,
        mimetype="application/octet-stream",
    )
    request = service.files().create(  # pylint: disable=no-member
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    )

    response = None
    last_bytes = 0

    while response is None:
        status = None
        for attempt in range(max_retries):
            try:
                status, response = request.next_chunk()
                break
            except (HttpError, OSError, ConnectionError) as error:
                if attempt == max_retries - 1:
                    raise error
                time.sleep(2 ** attempt)

        if status:
            current_bytes = int(status.progress() * file_size)
            delta = current_bytes - last_bytes
            last_bytes = current_bytes
            if progress and task_id is not None:
                progress.update(task_id, advance=delta)

    if progress and task_id is not None:
        progress.update(task_id, completed=file_size)

    return response.get("id"), response.get("webViewLink")