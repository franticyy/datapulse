import gzip
import tarfile
import zipfile
from pathlib import Path
from typing import Tuple


def verify_archive_integrity(file_path: Path | str) -> Tuple[bool, str]:
    """Zero-RAM verification for compressed archives (gzip, zip, tar).

    Pipes the byte stream through standard library decoders to validate
    CRC32 checksums, EOF markers, and central directories without disk extraction.
    """
    path = Path(file_path)
    if not path.is_file():
        return False, f"File not found: {path}"

    filename = path.name.lower()

    # Gzip / FASTQ.gz verification
    if filename.endswith(".gz"):
        try:
            with gzip.open(path, "rb") as gz_file:
                # Read in 1 MB chunks to calculate CRC32 & verify trailing ISIZE
                while chunk := gz_file.read(1024 * 1024):
                    pass
            return True, "Gzip stream integrity verified (CRC32/ISIZE match)."
        except gzip.BadGzipFile:
            return False, "Corrupted archive: Invalid gzip header or bad checksum."
        except EOFError:
            return False, "Corrupted archive: Truncated stream or missing EOF marker."
        except Exception as err:
            return False, f"Gzip stream verification failed: {err}"

    # ZIP verification
    elif filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(path, "r") as zip_ref:
                corrupted_member = zip_ref.testzip()
                if corrupted_member:
                    return False, f"Corrupted file inside archive: {corrupted_member}"
            return True, "ZIP central directory and member CRC32 verified."
        except zipfile.BadZipFile:
            return False, "Corrupted archive: Invalid ZIP format."
        except Exception as err:
            return False, f"ZIP verification failed: {err}"

    # TAR / TAR.GZ verification
    elif filename.endswith(".tar") or filename.endswith(".tar.gz") or filename.endswith(".tgz"):
        mode = "r:gz" if (filename.endswith(".tar.gz") or filename.endswith(".tgz")) else "r:"
        try:
            with tarfile.open(path, mode) as tar_ref:
                # Iterate through tar header blocks without unpacking payloads
                for _ in tar_ref:
                    pass
            return True, "TAR header blocks and metadata structures verified."
        except (tarfile.TarError, EOFError) as err:
            return False, f"Corrupted archive: TAR header validation failed ({err})."
        except Exception as err:
            return False, f"TAR verification failed: {err}"

    return True, "Uncompressed or non-standard archive (skipped stream validation)."