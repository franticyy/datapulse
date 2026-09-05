import requests


def fetch_ena_links(accession: str):
    """ENA Portal API'sinden FASTQ linklerini ve metagenom metadata alanlarini ceker."""
    url = "https://www.ebi.ac.uk/ena/portal/api/filereport"
    params = {
        "accession": accession,
        "result": "read_run",
        "fields": "run_accession,sample_accession,fastq_ftp,fastq_md5,experiment_title,sample_title,scientific_name",
        "format": "json",
        "download": "true"
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code != 200:
            return []

        records = response.json()
        results = []

        for row in records:
            fastq_str = row.get("fastq_ftp", "")
            md5_str = row.get("fastq_md5", "")
            if not fastq_str:
                continue

            fastq_urls = fastq_str.split(";")
            md5_hashes = md5_str.split(";") if md5_str else []

            for idx, f_url in enumerate(fastq_urls):
                if not f_url.startswith("http"):
                    f_url = f"https://{f_url.strip()}"
                
                results.append({
                    "url": f_url,
                    "fastq_url": f_url,
                    "filename": f_url.split("/")[-1],
                    "fastq_md5": md5_hashes[idx] if idx < len(md5_hashes) else None,
                    "run_accession": row.get("run_accession", ""),
                    "sample_accession": row.get("sample_accession", ""),
                    "experiment_title": row.get("experiment_title", ""),
                    "sample_title": row.get("sample_title", ""),
                    "scientific_name": row.get("scientific_name", "")
                })

        return results
    except Exception:
        return []