import requests


def generate_mirror_urls(fastq_ftp_path: str):
    # Başındaki ftp:// veya ftp.sra.ebi.ac.uk/ kısmını temizle
    clean_path = fastq_ftp_path.replace("ftp://", "").replace("ftp.sra.ebi.ac.uk/", "").lstrip("/")
    if not clean_path.startswith("vol1/"):
        clean_path = f"vol1/{clean_path}"

    return [
        # 1. AWS S3 Open Data Mirror
        f"https://era-public.s3.amazonaws.com/{clean_path}",
        # 2. EBI HTTPS Mirror (Çok hızlıdır ve ENA'nın doğrudan web aynasıdır)
        f"https://ftp.sra.ebi.ac.uk/{clean_path}",
        # 3. Standart FTP
        f"ftp://ftp.sra.ebi.ac.uk/{clean_path}",
    ]


def resolve_mirrors(accession: str):
    fields = [
        "study_accession",
        "sample_accession",
        "experiment_accession",
        "run_accession",
        "tax_id",
        "scientific_name",
        "fastq_ftp",
        "fastq_md5",
        "fastq_bytes",
    ]
    url = (
        f"https://www.ebi.ac.uk/ena/portal/api/filereport"
        f"?accession={accession}&result=read_run&fields={','.join(fields)}&format=json&download=false"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    records = []
    for item in data:
        fastq_ftps = item.get("fastq_ftp", "").split(";") if item.get("fastq_ftp") else []
        fastq_md5s = item.get("fastq_md5", "").split(";") if item.get("fastq_md5") else []
        fastq_sizes = item.get("fastq_bytes", "").split(";") if item.get("fastq_bytes") else []

        for idx, ftp_link in enumerate(fastq_ftps):
            if not ftp_link:
                continue
            filename = ftp_link.split("/")[-1]
            mirrors = generate_mirror_urls(ftp_link)

            record = {
                "name": filename,
                "filename": filename,
                "mirrors": mirrors,
                "stream_url": mirrors[0],
                "size": int(fastq_sizes[idx]) if idx < len(fastq_sizes) and fastq_sizes[idx] else None,
                "expected_md5": fastq_md5s[idx] if idx < len(fastq_md5s) else None,
                "study_accession": item.get("study_accession"),
                "sample_accession": item.get("sample_accession"),
                "experiment_accession": item.get("experiment_accession"),
                "run_accession": item.get("run_accession"),
                "scientific_name": item.get("scientific_name"),
                "tax_id": str(item.get("tax_id", "")),
            }
            records.append(record)

    return records

def resolve_optimal_mirror(url: str):
    """
    Verilen URL için en hızlı erişilebilir mirror'ı döner.
    ENA/SRA FTP linkleri için AWS S3 → EBI HTTPS sıralamasını dener.
    Normal HTTP/HTTPS URL'leri için doğrudan döner.

    Returns:
        (resolved_url: str, provider: str)
    """
    import urllib.parse

    parsed = urllib.parse.urlparse(url)

    # FTP veya EBI/SRA linkleri için mirror çözümle
    if parsed.scheme == "ftp" or "ebi.ac.uk" in parsed.netloc or "sra.ebi" in parsed.netloc:
        mirrors = generate_mirror_urls(url)
        for mirror in mirrors:
            try:
                resp = requests.head(mirror, timeout=5, allow_redirects=True)
                if resp.status_code < 400:
                    if "amazonaws.com" in mirror:
                        return mirror, "AWS Open Data"
                    elif "ebi.ac.uk" in mirror:
                        return mirror, "EBI HTTPS"
                    else:
                        return mirror, "FTP"
            except Exception:
                continue

    # Düz HTTP/HTTPS URL — direkt döndür
    return url, "Direct Origin"