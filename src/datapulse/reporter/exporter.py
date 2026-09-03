from pathlib import Path
from typing import List
import pandas as pd
from datapulse.validator.schema import DataRecord


def export_to_excel(
    records: List[DataRecord],
    output_dir: Path | str = "reports",
    filename: str = "summary_report.xlsx",
) -> Path:
    """Doğrulanmış kayıtları formatlı bir Excel tablosuna aktarır."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    target_file = out_path / filename

    # Pydantic modellerini sözlük listesine çevir
    data = [record.model_dump() for record in records]
    df = pd.DataFrame(data)

    # Excel dosyasına yaz (openpyxl motoruyla)
    with pd.ExcelWriter(target_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Valid Records")

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