import math
import os
import uuid
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth


class ProgressFileReader:
    """
    Dosyayı veya ilgili veri bloğunu okurken Rich ilerleme çubuğunu günceller.
    """
    def __init__(self, file_path: Path, offset: int = 0, length: int = None, progress=None, task_id=None, chunk_size: int = 64 * 1024):
        self.file_obj = open(file_path, "rb")
        self.offset = offset
        self.file_obj.seek(offset)
        self.remaining = length if length is not None else (file_path.stat().st_size - offset)
        self.progress = progress
        self.task_id = task_id
        self.chunk_size = chunk_size

    def read(self, size=-1):
        if self.remaining <= 0:
            return b""
        read_amount = self.chunk_size if size < 0 else min(size, self.chunk_size)
        read_amount = min(read_amount, self.remaining)
        
        data = self.file_obj.read(read_amount)
        if data:
            self.remaining -= len(data)
            if self.progress and self.task_id is not None:
                self.progress.update(self.task_id, advance=len(data))
        return data

    def close(self):
        self.file_obj.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class NextcloudSync:
    """
    Nextcloud WebDAV v2 API üzerinden kimlik doğrulamalı parçalı yükleme.
    """
    def __init__(self, base_url: str, username: str, app_password: str, chunk_size_mb: int = 10):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.auth = HTTPBasicAuth(username, app_password)
        self.chunk_size = chunk_size_mb * 1024 * 1024
        
        self.dav_files_url = f"{self.base_url}/remote.php/dav/files/{self.username}/"
        self.dav_uploads_url = f"{self.base_url}/remote.php/dav/uploads/{self.username}/"
        
        self.session = requests.Session()
        self.session.auth = self.auth

    def ensure_remote_dir(self, remote_dir: str):
        if not remote_dir or remote_dir == "/":
            return
        parts = [p for p in remote_dir.strip("/").split("/") if p]
        current_path = self.dav_files_url
        for part in parts:
            current_path = f"{current_path}{part}/"
            res = self.session.request("PROPFIND", current_path, headers={"Depth": "0"})
            if res.status_code == 404:
                self.session.request("MKCOL", current_path)

    def upload_file_chunked(self, local_path: str, remote_folder: str = "") -> bool:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"Dosya bulunamadı: {local_path}")

        file_size = path.stat().st_size
        if file_size <= self.chunk_size:
            return self._upload_simple(path, remote_folder)

        upload_id = f"datapulse-{uuid.uuid4().hex[:12]}"
        session_url = f"{self.dav_uploads_url}{upload_id}"
        
        res = self.session.request("MKCOL", session_url)
        if res.status_code not in (201, 405):
            raise RuntimeError(f"Yükleme oturumu başlatılamadı: HTTP {res.status_code}")

        total_chunks = math.ceil(file_size / self.chunk_size)

        with open(path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_data = f.read(self.chunk_size)
                chunk_name = f"{chunk_idx:010d}"
                chunk_url = f"{session_url}/{chunk_name}"

                headers = {
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(chunk_data)),
                }
                
                success = False
                for _ in range(3):
                    c_res = self.session.put(chunk_url, data=chunk_data, headers=headers)
                    if c_res.status_code in (200, 201, 204):
                        success = True
                        break
                
                if not success:
                    raise RuntimeError(f"Parça {chunk_idx + 1} iletilemedi.")

        if remote_folder:
            self.ensure_remote_dir(remote_folder)
            target_url = f"{self.dav_files_url}{remote_folder.strip('/')}/{path.name}"
        else:
            target_url = f"{self.dav_files_url}{path.name}"

        move_res = self.session.request("MOVE", f"{session_url}/.file", headers={"Destination": target_url})
        return move_res.status_code in (201, 204)

    def _upload_simple(self, path: Path, remote_folder: str) -> bool:
        if remote_folder:
            self.ensure_remote_dir(remote_folder)
            target_url = f"{self.dav_files_url}{remote_folder.strip('/')}/{path.name}"
        else:
            target_url = f"{self.dav_files_url}{path.name}"

        with open(path, "rb") as f:
            res = self.session.put(target_url, data=f, headers={"Content-Length": str(path.stat().st_size)})
            return res.status_code in (201, 204)

    def get_remote_checksum(self, remote_file_path: str) -> str:
        target_url = f"{self.dav_files_url}{remote_file_path.lstrip('/')}"
        headers = {"Depth": "0"}
        body = """<?xml version="1.0" encoding="utf-8" ?>
        <d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
          <d:prop>
            <oc:checksums/>
          </d:prop>
        </d:propfind>"""
        try:
            res = self.session.request("PROPFIND", target_url, headers=headers, data=body)
            if res.status_code in (200, 207):
                text = res.text
                if "MD5:" in text:
                    return text.split("MD5:")[1].split("<")[0].strip()
                if "SHA1:" in text:
                    return text.split("SHA1:")[1].split("<")[0].strip()
        except Exception:
            pass
        return ""


def upload_public_share(
    file_path: str,
    share_url: str = None,
    share_password: str = "",
    progress=None,
    task_id=None,
    **kwargs
) -> bool:
    """
    Nextcloud Public Share / File Drop yüklemesi.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")

    url = (
        share_url
        or kwargs.get("url")
        or kwargs.get("link")
        or kwargs.get("share_link")
        or kwargs.get("base_url")
        or os.getenv("NEXTCLOUD_SHARE_URL")
    )

    if not url or "/s/" not in url:
        raise ValueError("Geçerli bir Nextcloud paylaşım linki (/s/...) girilmelidir.")

    # 1. URL'den Domain ve Token ayrıştırma (ÖNCE BURASI ÇALIŞMALI)
    base_domain, token = url.rstrip("/").split("/s/")
    dav_url = f"{base_domain}/public.php/webdav/{path.name}"

    # 2. Şifre ve Doğrulama
    pwd = share_password or kwargs.get("password") or ""
    auth = HTTPBasicAuth(token, pwd)

    file_size = path.stat().st_size
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size),
    }

    # 3. Akışlı Yükleme (Progress Bar ile)
    with ProgressFileReader(path, progress=progress, task_id=task_id) as stream:
        res = requests.put(dav_url, data=stream, headers=headers, auth=auth, timeout=(30, None))

    if res.status_code in (200, 201, 204):
        return True
    else:
        raise RuntimeError(f"Yükleme başarısız oldu: HTTP {res.status_code} - {res.text[:200]}")