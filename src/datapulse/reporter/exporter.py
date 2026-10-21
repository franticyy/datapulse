from pathlib import Path
from typing import List, Union
import pandas as pd


def export_to_excel(
    records: List[Union[dict, object]],
    output_dir: Union[Path, str] = "reports",
    filename: str = "summary_report.xlsx",
) -> Path:
    """
    Doğrulanmış kayıtları formatlı bir Excel tablosuna aktarır.
    Pydantic model, ReportRecord (dict alt sınıfı) veya düz dict kabul eder.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    target_file = out_path / filename

    data = []
    for record in records:
        if hasattr(record, "model_dump"):
            data.append(record.model_dump())
        elif isinstance(record, dict):
            data.append(dict(record))
        else:
            data.append(vars(record))

    df = pd.DataFrame(data)

    # Raporlarda gösterilecek sütun sırası
    preferred_columns = [
        "filename", "size_bytes", "calculated_md5", "calculated_sha256",
        "verified", "status", "archive_status", "mirror_provider",
        "run_accession", "sample_accession", "study_accession", "scientific_name",
        "path", "error",
    ]
    cols = [c for c in preferred_columns if c in df.columns]
    extra = [c for c in df.columns if c not in cols]
    df = df[cols + extra]

    with pd.ExcelWriter(target_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Verified Records")

    return target_file


def generate_pipeline_summary(
    total_downloaded_bytes: int,
    valid_count: int,
    invalid_count: int,
    checksum_passed: bool,
) -> dict:
    """Pipeline operasyonunun özet metriklerini üretir."""
    return {
        "status": "SUCCESS" if checksum_passed and invalid_count == 0 else "WARNING",
        "downloaded_bytes": total_downloaded_bytes,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "checksum_verified": checksum_passed,
    }