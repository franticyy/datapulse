"""
Downloader modülleri için birim testleri.
Gerçek ağ istekleri mock ile simüle edilir.
"""
import gzip
import hashlib
import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from datapulse.downloader.stream import download_stream
from datapulse.downloader.mirror import generate_mirror_urls, resolve_optimal_mirror
from datapulse.downloader.parallel import _download_worker, _error_record, download_concurrently


def make_valid_gz(payload: bytes = b"ACGT" * 100) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(payload)
    return buf.getvalue()


def make_mock_response(status_code=200, content=b"DATA", headers=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = headers or {"content-length": str(len(content))}
    mock.iter_content = lambda chunk_size: iter([content])
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=status_code)
        )
    return mock


@pytest.fixture()
def tmp_dest(tmp_path) -> str:
    return str(tmp_path / "output.fastq.gz")


@pytest.fixture()
def existing_partial(tmp_path) -> str:
    p = tmp_path / "partial.fastq.gz"
    p.write_bytes(b"PARTIAL")
    return str(p)


class TestDownloadStream:
    def test_fresh_download(self, tmp_dest):
        content = b"ACGT" * 256
        mock_resp = make_mock_response(200, content)
        with patch("datapulse.downloader.stream.requests.get", return_value=mock_resp):
            result = download_stream("https://example.com/file.gz", tmp_dest)
        assert result == tmp_dest
        assert Path(tmp_dest).read_bytes() == content

    def test_resume_sends_range_header(self, existing_partial):
        content = b"_RESUMED"
        mock_resp = make_mock_response(206, content, headers={"content-length": str(len(content))})
        with patch("datapulse.downloader.stream.requests.get", return_value=mock_resp) as mock_get:
            download_stream("https://example.com/file.gz", existing_partial)
        _, kwargs = mock_get.call_args
        assert "Range" in kwargs["headers"]
        assert kwargs["headers"]["Range"] == f"bytes={len(b'PARTIAL')}-"

    def test_timeout_raises(self, tmp_dest):
        with patch("datapulse.downloader.stream.requests.get", side_effect=requests.Timeout):
            with pytest.raises(requests.Timeout):
                download_stream("https://example.com/file.gz", tmp_dest)

    def test_http_error_raises(self, tmp_dest):
        mock_resp = make_mock_response(404)
        with patch("datapulse.downloader.stream.requests.get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                download_stream("https://example.com/file.gz", tmp_dest)

    def test_progress_updated(self, tmp_dest):
        mock_resp = make_mock_response(200, b"DATA")
        mock_progress = MagicMock()
        with patch("datapulse.downloader.stream.requests.get", return_value=mock_resp):
            download_stream("https://example.com/file.gz", tmp_dest,
                            progress=mock_progress, task_id=0)
        mock_progress.update.assert_called()

    def test_uses_correct_timeout(self, tmp_dest):
        mock_resp = make_mock_response(200, b"X")
        with patch("datapulse.downloader.stream.requests.get", return_value=mock_resp) as mock_get:
            download_stream("https://example.com/file.gz", tmp_dest)
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == (30, None)


class TestGenerateMirrorUrls:
    def test_returns_three_mirrors(self):
        assert len(generate_mirror_urls("vol1/fastq/ERR123/ERR123.fastq.gz")) == 3

    def test_aws_mirror_first(self):
        assert "amazonaws.com" in generate_mirror_urls("vol1/fastq/ERR123/ERR123.fastq.gz")[0]

    def test_ebi_https_second(self):
        assert "https://ftp.sra.ebi.ac.uk" in generate_mirror_urls("vol1/fastq/ERR123/ERR123.fastq.gz")[1]

    def test_ftp_third(self):
        assert generate_mirror_urls("vol1/fastq/ERR123/ERR123.fastq.gz")[2].startswith("ftp://")

    def test_strips_ftp_prefix(self):
        mirrors = generate_mirror_urls("ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123.fastq.gz")
        assert all("ERR123.fastq.gz" in m for m in mirrors)

    def test_adds_vol1_prefix_if_missing(self):
        mirrors = generate_mirror_urls("fastq/ERR123/ERR123.fastq.gz")
        assert all("vol1" in m for m in mirrors[:2])


class TestResolveOptimalMirror:
    def test_plain_https_returns_direct(self):
        url = "https://example.com/data.fastq.gz"
        resolved, provider = resolve_optimal_mirror(url)
        assert resolved == url
        assert provider == "Direct Origin"

    def test_ftp_url_tries_mirrors(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("datapulse.downloader.mirror.requests.head", return_value=mock_resp):
            _, provider = resolve_optimal_mirror(
                "ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123.fastq.gz"
            )
        assert provider in ("AWS Open Data", "EBI HTTPS", "FTP")

    def test_all_mirrors_fail_returns_original(self):
        with patch("datapulse.downloader.mirror.requests.head", side_effect=Exception("timeout")):
            url = "ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR/ERR.fastq.gz"
            resolved, provider = resolve_optimal_mirror(url)
        assert resolved == url
        assert provider == "Direct Origin"


class TestDownloadWorker:
    def _make_progress(self):
        p = MagicMock()
        p.update = MagicMock()
        p.start_task = MagicMock()
        return p

    def test_successful_download_and_verify(self, tmp_path):
        content = make_valid_gz()
        md5 = hashlib.md5(content).hexdigest()
        mock_resp = make_mock_response(200, content)
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            result = _download_worker(
                item={"url": "https://example.com/ERR123.fastq.gz", "expected_md5": md5},
                output_dir=tmp_path,
                progress=self._make_progress(),
                task_id=0,
            )
        assert result["success"] is True
        assert result["verified"] is True

    def test_wrong_md5_deletes_file(self, tmp_path):
        content = make_valid_gz()
        mock_resp = make_mock_response(200, content)
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            result = _download_worker(
                item={"url": "https://example.com/ERR123.fastq.gz",
                      "expected_md5": "000wronghash000"},
                output_dir=tmp_path,
                progress=self._make_progress(),
                task_id=0,
            )
        assert result["success"] is False
        assert not (tmp_path / "ERR123.fastq.gz").exists()

    def test_http_error_returns_error_record(self, tmp_path):
        mock_resp = make_mock_response(403)
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            result = _download_worker(
                item={"url": "https://example.com/ERR123.fastq.gz"},
                output_dir=tmp_path,
                progress=self._make_progress(),
                task_id=0,
            )
        assert result["success"] is False
        assert "HTTP" in result["error"]

    def test_timeout_returns_error_record(self, tmp_path):
        with patch("datapulse.downloader.parallel.requests.get", side_effect=requests.Timeout):
            result = _download_worker(
                item={"url": "https://example.com/ERR123.fastq.gz"},
                output_dir=tmp_path,
                progress=self._make_progress(),
                task_id=0,
            )
        assert result["success"] is False
        assert "zaman aşımı" in result["error"]

    def test_416_already_downloaded(self, tmp_path):
        existing = tmp_path / "ERR123.fastq.gz"
        existing.write_bytes(b"COMPLETE")
        mock_resp = make_mock_response(416, b"")
        mock_resp.raise_for_status = MagicMock()
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            result = _download_worker(
                item={"url": "https://example.com/ERR123.fastq.gz"},
                output_dir=tmp_path,
                progress=self._make_progress(),
                task_id=0,
            )
        assert result["filename"] == "ERR123.fastq.gz"


class TestErrorRecord:
    def test_structure(self):
        rec = _error_record("file.gz", "https://example.com/file.gz", "timeout")
        assert rec["success"] is False
        assert rec["verified"] is False
        assert rec["error"] == "timeout"
        assert rec["size_bytes"] == 0


class TestDownloadConcurrently:
    def test_returns_result_per_item(self, tmp_path):
        content = make_valid_gz()
        mock_resp = make_mock_response(200, content)
        items = [
            {"url": "https://example.com/file1.fastq.gz"},
            {"url": "https://example.com/file2.fastq.gz"},
        ]
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            results = download_concurrently(items, output_dir=str(tmp_path), max_workers=2)
        assert len(results) == 2

    def test_creates_output_dir(self, tmp_path):
        new_dir = str(tmp_path / "new" / "downloads")
        mock_resp = make_mock_response(200, b"X")
        with patch("datapulse.downloader.parallel.requests.get", return_value=mock_resp):
            download_concurrently([{"url": "https://example.com/f.txt"}], output_dir=new_dir)
        assert os.path.isdir(new_dir)