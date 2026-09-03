from typing import Tuple
import httpx


def resolve_optimal_mirror(url: str, timeout: float = 5.0) -> Tuple[str, str]:
    """Inspects target download URL and resolves to high-throughput cloud mirrors

    (e.g., AWS Open Data / NCBI) when available, falling back to origin.

    Returns:
        Tuple[str, str]: (resolved_url, provider_name)
    """
    clean_url = url.strip()

    # ENA FASTQ -> AWS Open Data SRA/FASTQ mirror mapping
    # ENA FASTQ path: ftp.sra.ebi.ac.uk/vol1/fastq/...
    if "ftp.sra.ebi.ac.uk" in clean_url:
        # Construct AWS Open Data S3 public HTTP mirror candidate
        aws_candidate = clean_url.replace(
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
            pass  # Fall back to origin if mirror check times out or fails

        return clean_url, "ENA Primary Origin (EBI)"

    return clean_url, "Direct Origin"