import gzip
from pathlib import Path
from datapulse.validator.checksum import calculate_hash, verify_checksum
from datapulse.validator.archive import verify_archive_integrity
from datapulse.reporter.certificate import generate_data_certificate
from datapulse.downloader.mirror import resolve_optimal_mirror



def test_checksum_verification(tmp_path: Path):
    """Verify MD5 and SHA-256 calculation and validation logic."""
    test_file = tmp_path / "sample.txt"
    test_file.write_text("DataPulse Resilient Engine Test Data", encoding="utf-8")

    sha256 = calculate_hash(test_file, algorithm="sha256")
    md5 = calculate_hash(test_file, algorithm="md5")

    assert len(sha256) == 64
    assert len(md5) == 32
    assert verify_checksum(test_file, sha256, algorithm="sha256") is True
    assert verify_checksum(test_file, md5, algorithm="md5") is True
    assert verify_checksum(test_file, "invalid_hash_value", algorithm="md5") is False


def test_archive_integrity_valid_and_corrupt(tmp_path: Path):
    """Verify zero-RAM archive integrity detector on both clean and corrupted streams."""
    valid_gz = tmp_path / "valid.fastq.gz"
    with gzip.open(valid_gz, "wb") as f:
        f.write(b"@SEQ1\nACGTACGT\n+\nIIIIIIII\n")

    is_valid, msg = verify_archive_integrity(valid_gz)
    assert is_valid is True
    assert "verified" in msg.lower()

    # Create deliberately corrupted gzip stream (invalid bytes / truncated)
    corrupt_gz = tmp_path / "corrupt.fastq.gz"
    corrupt_gz.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\xab\xcd\xef")

    is_corrupt_valid, corrupt_msg = verify_archive_integrity(corrupt_gz)
    assert is_corrupt_valid is False
    assert "corrupted" in corrupt_msg.lower() or "truncated" in corrupt_msg.lower()


def test_certificate_generation(tmp_path: Path):
    """Verify JSON audit manifest and dark HTML certificate generation."""
    mock_records = [
        {
            "filename": "sample_1.fastq.gz",
            "size_bytes": 1048576,
            "source_url": "https://example.com/sample_1.fastq.gz",
            "calculated_md5": "d41d8cd98f00b204e9800998ecf8427e",
            "calculated_sha256": "",
            "verified": True,
            "archive_status": "Gzip stream integrity verified.",
        }
    ]

    out_dir = tmp_path / "reports"
    certs = generate_data_certificate(mock_records, output_dir=str(out_dir))

    assert Path(certs["json"]).exists()
    assert Path(certs["html"]).exists()
    assert "sample_1.fastq.gz" in Path(certs["html"]).read_text(encoding="utf-8")


def test_mirror_resolution_fallback():
    """Verify that regular URLs return Direct Origin and unavailable mirrors fallback safely."""
    test_url = "https://raw.githubusercontent.com/torvalds/linux/master/README"
    resolved_url, provider = resolve_optimal_mirror(test_url)

    assert resolved_url == test_url
    assert provider == "Direct Origin"