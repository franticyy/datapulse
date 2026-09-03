from typing import List, Dict
from urllib.parse import urljoin
import re
import httpx
from bs4 import BeautifulSoup


def fetch_ena_links(accession_id: str, title_keyword: str = "") -> List[Dict[str, str]]:
    """
    ENA Portal API'sini sorgulayarak çalışmaya/örneğe ait FASTQ linklerini
    ve resmi MD5 hash değerlerini çeker.
    """
    api_url = "https://www.ebi.ac.uk/ena/portal/api/filereport"
    params = {
        "accession": accession_id,
        "result": "read_run",
        "fields": "run_accession,sample_accession,fastq_ftp,fastq_md5,scientific_name",
        "format": "json",
        "download": "false",
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()

    matched_items = []
    keyword_lower = title_keyword.strip().lower()

    for entry in data:
        fastq_paths = entry.get("fastq_ftp", "")
        if not fastq_paths:
            continue

        md5_list = entry.get("fastq_md5", "").split(";")
        urls = fastq_paths.split(";")
        run_acc = entry.get("run_accession", "")
        sample_title = entry.get("scientific_name", "") or entry.get("sample_accession", "")

        # Anahtar kelime filtrelemesi (Scientific name veya Run ID içinde arar)
        combined_text = f"{run_acc} {sample_title}".lower()
        if keyword_lower and keyword_lower not in combined_text:
            continue

        for idx, ftp_url in enumerate(urls):
            # ENA genelde "ftp.sra.ebi.ac.uk/..." döner, HTTPS formatına çeviriyoruz
            cleaned_url = ftp_url.strip()
            if not cleaned_url.startswith("http"):
                cleaned_url = f"https://{cleaned_url}"

            filename = cleaned_url.split("/")[-1]
            file_md5 = md5_list[idx] if idx < len(md5_list) else ""

            matched_items.append({
                "title": f"{run_acc} ({sample_title}) - {filename}",
                "url": cleaned_url,
                "extension": "fastq.gz",
                "expected_md5": file_md5,
            })

    return matched_items


def discover_download_links(
    page_url: str,
    title_keyword: str = "",
    target_extensions: tuple = (
        ".pdf", ".csv", ".xlsx", ".zip", ".tar.gz", ".json", ".txt", ".bin", ".fastq.gz", ".fq.gz"
    ),
) -> List[Dict[str, str]]:
    """
    Genel web sayfalarını BeautifulSoup ile, ENA linklerini ise doğrudan Portal API ile işler.
    """
    # 1. ENA Browser linki mi kontrol et (örn: https://www.ebi.ac.uk/ena/browser/view/PRJNA...)
    ena_match = re.search(r"(PRJ[E,N,D][A-Z][0-9]+|[E,S,D]RR[0-9]+|[E,S,D]RX[0-9]+)", page_url)
    if "ebi.ac.uk/ena" in page_url and ena_match:
        accession_id = ena_match.group(1)
        return fetch_ena_links(accession_id, title_keyword=title_keyword)

    # 2. Standart Web Sitesi Scraper Akışı
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.get(page_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    found_items = []
    seen_urls = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        link_text = tag.get_text(strip=True)
        link_title = tag.get("title", "").strip()

        absolute_url = urljoin(page_url, href)
        if absolute_url in seen_urls:
            continue

        url_lower = absolute_url.lower()
        keyword_lower = title_keyword.strip().lower()

        matches_extension = any(url_lower.endswith(ext) or (ext + "?") in url_lower for ext in target_extensions)
        combined_text = f"{link_text} {link_title} {href}".lower()
        matches_keyword = keyword_lower in combined_text if keyword_lower else True

        if matches_extension and matches_keyword:
            display_title = link_text or link_title or absolute_url.split("/")[-1]
            found_items.append({
                "title": display_title,
                "url": absolute_url,
                "extension": url_lower.split("?")[0].split(".")[-1],
                "expected_md5": "",
            })
            seen_urls.add(absolute_url)

    return found_items