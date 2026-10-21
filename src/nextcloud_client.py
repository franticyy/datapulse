import math
import os
import uuid
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth


class NextcloudSync:
    def __init__(self, base_url: str, username: str, app_password: str, chunk_size_mb: int = 10):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.auth = HTTPBasicAuth(username, app_password)
        self.chunk_size = chunk_size_mb * 1024 * 1024  # Bayt cinsinden parça boyutu
        
        # Standart ve Parçalı (Uploads) WebDAV uç noktaları
        self.dav_files_url = f"{self.base_url}/remote.php/dav/files/{self.username}/"
        self.dav_uploads_url = f"{self.base_url}/remote.php/dav/uploads/{self.username}/"
        
        self.session = requests.Session()
        self.session.auth = self.auth

    def test_connection(self) -> bool:
        try:
            res = self.session.request("PROPFIND", self.dav_files_url, headers={"Depth": "0"})
            return res.status_code in (200, 207)
        except requests.RequestException:
            return False

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
        """
        Nextcloud Chunking v2 API kullanarak dosyayı parçalı yükler.
        Ağ bağlantısı kopsa dahi bellek şişmez ve her blok ayrı doğrulanır.
        """
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"Dosya bulunamadı: {local_path}")

        file_size = path.stat().st_size
        
        # 10 MB'dan küçükse doğrudan tek seferde gönder
        if file_size <= self.chunk_size:
            return self._upload_simple(path, remote_folder)

        # 1. Aşama: Nextcloud üzerinde geçici bir upload oturumu oluştur (MKCOL)
        upload_id = f"datapulse-{uuid.uuid4().hex[:12]}"
        session_url = f"{self.dav_uploads_url}{upload_id}"
        
        res = self.session.request("MKCOL", session_url)
        if res.status_code not in (201, 405):
            raise RuntimeError(f"Yükleme oturumu başlatılamadı: HTTP {res.status_code}")

        total_chunks = math.ceil(file_size / self.chunk_size)
        print(f"[{path.name}] Toplam {total_chunks} parça halinde yükleniyor...")

        # 2. Aşama: Parçaları sırayla stream et
        with open(path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_data = f.read(self.chunk_size)
                # Nextcloud v2 isimlendirme formatı: 00000, 00001 ...
                chunk_name = f"{chunk_idx:010d}"
                chunk_url = f"{session_url}/{chunk_name}"

                headers = {
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(chunk_data)),
                }
                
                # Tekrar deneme mantığı (Retry)
                success = False
                for attempt in range(3):
                    c_res = self.session.put(chunk_url, data=chunk_data, headers=headers)
                    if c_res.status_code in (200, 201, 204):
                        success = True
                        break
                    print(f"Parça {chunk_idx + 1}/{total_chunks} başarısız (Deneme {attempt + 1}). Tekrar deneniyor...")

                if not success:
                    raise RuntimeError(f"Parça {chunk_idx + 1} yüklenirken transfer koptu.")

                print(f"-> Parça {chunk_idx + 1}/{total_chunks} iletildi (%{int(((chunk_idx + 1) / total_chunks) * 100)})")

        # 3. Aşama: Parçaları hedef klasörde birleştir (MOVE isteği)
        if remote_folder:
            self.ensure_remote_dir(remote_folder)
            target_url = f"{self.dav_files_url}{remote_folder.strip('/')}/{path.name}"
        else:
            target_url = f"{self.dav_files_url}{path.name}"

        move_res = self.session.request(
            "MOVE",
            f"{session_url}/.file",
            headers={"Destination": target_url}
        )

        if move_res.status_code in (201, 204):
            print(f"[{path.name}] Birleştirme başarılı, dosya Nextcloud'a yerleştirildi.")
            return True
        else:
            raise RuntimeError(f"Birleştirme adımı başarısız: HTTP {move_res.status_code} - {move_res.text}")

    def _upload_simple(self, path: Path, remote_folder: str) -> bool:
        """Küçük dosyalar için standart akış yüklemesi."""
        if remote_folder:
            self.ensure_remote_dir(remote_folder)
            target_url = f"{self.dav_files_url}{remote_folder.strip('/')}/{path.name}"
        else:
            target_url = f"{self.dav_files_url}{path.name}"

        with open(path, "rb") as f:
            res = self.session.put(target_url, data=f, headers={"Content-Length": str(path.stat().st_size)})
            return res.status_code in (201, 204)

    def get_remote_checksum(self, remote_file_path: str) -> str:
        """Nextcloud üzerindeki dosyanın MD5/SHA256 hash değerini döner."""
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
                for part in text.split():
                    if "MD5:" in part:
                        return part.split("MD5:")[1].split("<")[0].strip()
                    if "SHA256:" in part:
                        return part.split("SHA256:")[1].split("<")[0].strip()
        except Exception as e:
            print(f"Uzak hash alınamadı: {e}")
        return ""