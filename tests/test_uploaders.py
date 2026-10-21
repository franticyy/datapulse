"""
Upload modülleri için birim testleri.
Gerçek ağ/kimlik doğrulama gerektiren fonksiyonlar mock ile test edilir.
"""
import gzip
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from datapulse.uploader.nextcloud import ProgressFileReader, upload_public_share
from datapulse.uploader.s3 import upload_s3, ProgressPercentage
from datapulse.uploader.ena_ftp import upload_ena_ftp
from datapulse.scraper.gdrive import parse_gdrive_url, get_gdrive_direct_download_url


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    gz_path = tmp_path / "sample.fastq.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"@SEQ1\nACGT\n+\nIIII\n")
    return gz_path


@pytest.fixture()
def plain_file(tmp_path: Path) -> Path:
    p = tmp_path / "report.txt"
    p.write_text("DataPulse test report", encoding="utf-8")
    return p


class TestProgressFileReader:
    def test_reads_full_file(self, plain_file):
        with ProgressFileReader(plain_file) as reader:
            data = b""
            while True:
                chunk = reader.read(64)
                if not chunk:
                    break
                data += chunk
        assert data == plain_file.read_bytes()

    def test_progress_callback_called(self, plain_file):
        mock_progress = MagicMock()
        with ProgressFileReader(plain_file, progress=mock_progress, task_id=0) as reader:
            reader.read(1024)
        mock_progress.update.assert_called()

    def test_empty_read_at_eof(self, plain_file):
        size = plain_file.stat().st_size
        with ProgressFileReader(plain_file, offset=size) as reader:
            assert reader.read(64) == b""


class TestNextcloudUpload:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            upload_public_share(
                file_path=str(tmp_path / "nonexistent.gz"),
                share_url="https://cloud.example.com/s/TOKEN123",
            )

    def test_invalid_share_url_raises(self, plain_file):
        with pytest.raises(ValueError, match="Nextcloud"):
            upload_public_share(
                file_path=str(plain_file),
                share_url="https://cloud.example.com/no-token-here",
            )

    def test_successful_upload(self, plain_file):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        with patch("datapulse.uploader.nextcloud.requests.put", return_value=mock_resp) as mock_put:
            result = upload_public_share(
                file_path=str(plain_file),
                share_url="https://cloud.example.com/s/TOKEN123",
                share_password="",
            )
        assert result is True
        mock_put.assert_called_once()
        _, kwargs = mock_put.call_args
        assert kwargs["timeout"] == (30, None)

    def test_server_error_raises(self, plain_file):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("datapulse.uploader.nextcloud.requests.put", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                upload_public_share(
                    file_path=str(plain_file),
                    share_url="https://cloud.example.com/s/TOKEN123",
                )


class TestS3Upload:
    def test_progress_percentage_callback(self):
        mock_progress = MagicMock()
        cb = ProgressPercentage(progress=mock_progress, task_id=1)
        cb(512)
        mock_progress.update.assert_called_once_with(1, advance=512)

    def test_progress_percentage_no_progress(self):
        cb = ProgressPercentage()
        cb(512)  # exception yok

    def test_upload_s3_calls_boto3(self, plain_file):
        mock_s3 = MagicMock()
        with patch("datapulse.uploader.s3.boto3.client", return_value=mock_s3):
            result = upload_s3(
                file_path=str(plain_file),
                bucket_name="test-bucket",
                aws_access_key="AKIATEST",
                aws_secret_key="secret",
                region_name="us-east-1",
            )
        mock_s3.upload_file.assert_called_once()
        assert result == "s3://test-bucket/report.txt"

    def test_upload_s3_custom_object_key(self, plain_file):
        mock_s3 = MagicMock()
        with patch("datapulse.uploader.s3.boto3.client", return_value=mock_s3):
            result = upload_s3(
                file_path=str(plain_file),
                bucket_name="genomics",
                object_key="uploads/2026/report.txt",
                aws_access_key="KEY",
                aws_secret_key="SECRET",
            )
        assert result == "s3://genomics/uploads/2026/report.txt"


class TestEnaFtpUpload:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            upload_ena_ftp(
                file_path=str(tmp_path / "missing.fastq.gz"),
                username="Webin-12345",
                password="pass",
            )

    def test_ftp_success(self, plain_file):
        mock_ftp = MagicMock()
        with patch("datapulse.uploader.ena_ftp.FTP", return_value=mock_ftp):
            result = upload_ena_ftp(
                file_path=str(plain_file),
                username="Webin-12345",
                password="testpass",
            )
        assert result is True
        mock_ftp.connect.assert_called_once()
        mock_ftp.login.assert_called_once_with(user="Webin-12345", passwd="testpass")
        mock_ftp.storbinary.assert_called_once()

    def test_ftp_auth_failure_falls_back_to_ftps(self, plain_file):
        from ftplib import error_perm
        mock_ftp = MagicMock()
        mock_ftp.login.side_effect = error_perm("530 Login incorrect")
        mock_ftps = MagicMock()
        with patch("datapulse.uploader.ena_ftp.FTP", return_value=mock_ftp), \
             patch("datapulse.uploader.ena_ftp.FTP_TLS", return_value=mock_ftps):
            result = upload_ena_ftp(
                file_path=str(plain_file),
                username="Webin-12345",
                password="testpass",
            )
        assert result is True
        mock_ftps.auth.assert_called_once()
        mock_ftps.prot_p.assert_called_once()

    def test_both_protocols_fail_raises(self, plain_file):
        from ftplib import error_perm
        mock_ftp = MagicMock()
        mock_ftp.login.side_effect = error_perm("530 Login incorrect")
        mock_ftps = MagicMock()
        mock_ftps.login.side_effect = error_perm("530 Login incorrect")
        with patch("datapulse.uploader.ena_ftp.FTP", return_value=mock_ftp), \
             patch("datapulse.uploader.ena_ftp.FTP_TLS", return_value=mock_ftps):
            with pytest.raises(PermissionError, match="kimlik doğrulama başarısız"):
                upload_ena_ftp(
                    file_path=str(plain_file),
                    username="Webin-12345",
                    password="wrongpass",
                )


class TestGdriveHelpers:
    def test_parse_folder_url(self):
        url = "https://drive.google.com/drive/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        kind, fid = parse_gdrive_url(url)
        assert kind == "folder"
        assert fid == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    def test_parse_file_url(self):
        url = "https://drive.google.com/file/d/1A2B3C4D5E/view"
        kind, fid = parse_gdrive_url(url)
        assert kind == "file"
        assert fid == "1A2B3C4D5E"

    def test_parse_query_param_url(self):
        url = "https://drive.google.com/open?id=XYZ789"
        kind, fid = parse_gdrive_url(url)
        assert kind == "file"
        assert fid == "XYZ789"

    def test_parse_non_gdrive_url(self):
        kind, fid = parse_gdrive_url("https://example.com/file.gz")
        assert kind is None
        assert fid is None

    def test_direct_download_url_format(self):
        url = get_gdrive_direct_download_url("ABC123")
        assert "ABC123" in url
        assert url.startswith("https://drive.google.com")
        assert "export=download" in url