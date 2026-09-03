import gzip
from pathlib import Path
from datapulse.validator.checksum import calculate_hash, verify_checksum
from datapulse.validator.archive import verify_archive_integrity
from datapulse.reporter.certificate import generate_data_certificate


def test_checksum_verification(tmp_path: Path):
    """MD5 ve SHA-256 hash hesaplama ve doğrulama testi."""
    test_file = tmp_path / "sample.txt"
    test_file.write_text("DataPulse Resilient Engine Test Data", encoding="utf-8")

    # Bilinen hash doğrulaması
    sha256 = calculate_hash(test_file, algorithm="sha256")
    md5 = calculate_hash(test_file, algorithm="md5")

    assert len(sha256) == 64
    assert len(md5) == 32
    assert verify_checksum(test_file, sha256, algorithm="sha256") is True
    assert verify_checksum(test_file, md5, algorithm="md5") is True
    assert verify_checksum(test_file, "invalid_hash_value", algorithm="md5") is False


def test_archive_integrity_valid_and_corrupt(tmp_path: Path):
    """Gzip arşiv doğrulama motorunun sağlam ve bozuk dosyaları yakalama testi."""
    valid_gz = tmp_path / "valid.fastq.gz"
    with gzip.open(valid_gz, "wb") as f:
        f.write(b"@SEQ1\nACGTACGT\n+\nIIIIIIII\n")

    is_valid, msg = verify_archive_integrity(valid_gz)
    assert is_valid is True
    assert "bütünlüğü doğrulandı" in msg

    # Bilerek bozulmuş (truncated / bozuk baytlı) gzip oluştur
    corrupt_gz = tmp_path / "corrupt.fastq.gz"
    corrupt_gz.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\xab\xcd\xef")  # Eksik/bozuk arşiv

    is_corrupt_valid, corrupt_msg = verify_archive_integrity(corrupt_gz)
    assert is_corrupt_valid is False
    assert "Bozuk arşiv" in corrupt_msg or "Eksik dosya" in corrupt_msg


def test_certificate_generation(tmp_path: Path):
    """JSON manifest ve HTML sertifika üretim testi."""
    mock_records = [
        {
            "filename": "sample_1.fastq.gz",
            "size_bytes": 1048576,
            "source_url": "https://example.com/sample_1.fastq.gz",
            "calculated_md5": "d41d8cd98f00b204e9800998ecf8427e",
            "calculated_sha256": "",
            "verified": True,
            "archive_status": "Gzip akış CRC32 doğrulandı.",
        }
    ]

    out_dir = tmp_path / "reports"
    certs = generate_data_certificate(mock_records, output_dir=str(out_dir))

    assert Path(certs["json"]).exists()
    assert Path(certs["html"]).exists()
    assert "sample_1.fastq.gz" in Path(certs["html"]).read_text(encoding="utf-8")