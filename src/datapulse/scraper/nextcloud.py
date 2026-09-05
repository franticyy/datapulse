import xml.etree.ElementTree as ET
from urllib.parse import quote, urljoin, urlparse
import requests


def parse_nextcloud_share_url(share_url: str):
    """Nextcloud / ownCloud paylasim linkinden base_url ve token cikarir."""
    parsed = urlparse(share_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    parts = parsed.path.strip("/").split("/")
    if "s" in parts:
        idx = parts.index("s")
        if idx + 1 < len(parts):
            token = parts[idx + 1]
            return base_url, token
    return None, None


def list_nextcloud_files(share_url: str):
    """Nextcloud acik paylasim linkindeki dosyalari WebDAV uzerinden listeler

    ve her dosya icin dogrudan (public auth gerektirmeyen) indirme linki uretir.
    """
    base_url, token = parse_nextcloud_share_url(share_url)
    if not base_url or not token:
        return []

    webdav_url = urljoin(base_url, "public.php/webdav/")

    headers = {"Depth": "1"}
    response = requests.request(
        "PROPFIND",
        webdav_url,
        auth=(token, ""),
        headers=headers,
        timeout=15,
    )

    if response.status_code not in (200, 207):
        return []

    root = ET.fromstring(response.content)
    namespaces = {"d": "DAV:"}
    files = []

    for resp in root.findall("d:response", namespaces):
        href = resp.find("d:href", namespaces)
        if href is None or not href.text:
            continue

        href_path = href.text

        resourcetype = resp.find(".//d:resourcetype", namespaces)
        is_collection = (
            resourcetype is not None
            and resourcetype.find("d:collection", namespaces) is not None
        )

        if href_path.rstrip("/").endswith("webdav") or is_collection:
            continue

        filename = href_path.rstrip("/").split("/")[-1]
        public_download_url = f"{base_url}/index.php/s/{token}/download?files={quote(filename)}"

        content_length = resp.find(".//d:getcontentlength", namespaces)
        size_bytes = int(content_length.text) if content_length is not None else 0

        files.append({
            "filename": filename,
            "url": public_download_url,
            "size": size_bytes,
        })

    return files