import re
from typing import Optional, Tuple
import httpx


def extract_run_accession(text: str) -> Optional[str]:
    """Extracts SRA/ENA/DRA run accession identifiers (e.g., ERR1234567, SRR987654)

    from raw strings, URLs, or browser view paths.
    """
    match = re.search(r"\b([SED]RR\d{6,9})\b", text.strip())
    return match.group(1) if match else None


def resolve_optimal_mirror(url_or_query: str, timeout: float = 5.0) -> Tuple[str, str]:
    """Inspects target download URL or accession identifier and resolves to

    high-throughput cloud mirrors (AWS Open Data / S3) when available,
    falling back to origin if unreachable.

    Returns:
        Tuple[str, str]: (resolved_url, provider_name)
    """
    clean_target = url_or_query.strip()
    accession = extract_run_accession(clean_target)

    # 1. ENA Browser View URL or raw Run Accession -> AWS Open Data S3 Mirror
    if accession and ("ena/browser/view" in clean_target or not clean_target.startswith("http")):
        aws_candidate = f"https://sra-pub-run-odp.s3.amazonaws.com/sra/{accession}/{accession}"
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.head(aws_candidate)
                if resp.status_code == 200:
                    return aws_candidate, f"AWS Open Data S3 Mirror ({accession})"
        except Exception:
            pass  # Fall back if mirror check fails

    # 2. Direct ENA FTP/HTTP FASTQ URL -> AWS S3 / Mirror mapping
    if "ftp.sra.ebi.ac.uk" in clean_target:
        aws_candidate = clean_target.replace(
            "https://ftp.sra.ebi.ac.uk", "https://sra-pub-run-odp.s3.amazonaws.com"
        ).replace(
            "http://ftp.sra.ebi.ac.uk", "https://sra-pub-run-odp.s3.amazonaws.com"
        )
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.head(aws_candidate)
                if resp.status_code == 200:
                    return aws_candidate, "AWS Open Data (S3 Mirror)"
        except Exception:
            pass

        return clean_target, "ENA Primary Origin (EBI)"

    return clean_target, "Direct Origin"