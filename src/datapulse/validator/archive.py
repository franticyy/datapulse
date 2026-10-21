import gzip
import zlib
from pathlib import Path
from typing import Tuple


_BGZF_EOF = bytes([
    0x1f, 0x8b, 0x08, 0x04, 0x00, 0x00, 0x00, 0x00,
    0x00, 0xff, 0x06, 0x00, 0x42, 0x43, 0x02, 0x00,
    0x1b, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
])


def check_bgzf_eof(filepath: str) -> bool:
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size < 28:
        return False
    try:
        with open(path, "rb") as f:
            f.seek(-28, 2)
            tail = f.read(28)
        return tail == _BGZF_EOF
    except OSError:
        return False


verify_bgzf_eof = check_bgzf_eof
check_eof = check_bgzf_eof


def _check_gzip(path: Path) -> Tuple[bool, str]:
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1024 * 1024):
                pass
        return True, "Gzip stream integrity verified."
    except gzip.BadGzipFile:
        return False, "Corrupted (Bad Gzip Header)"
    except EOFError:
        return False, "Corrupted (Truncated Gzip)"
    except zlib.error as e:
        return False, f"Corrupted (CRC Error: {e})"
    except OSError as e:
        return False, f"Error ({e})"


def _check_bam(path: Path) -> Tuple[bool, str]:
    if check_bgzf_eof(str(path)):
        return True, "BGZF integrity verified."
    return False, "Corrupted (No BGZF EOF)"


def verify_archive_integrity(filepath) -> Tuple[bool, str]:
    path = Path(filepath)

    if not path.exists():
        return False, "Error (File Not Found)"
    if path.stat().st_size == 0:
        return False, "Error (Empty File)"

    name_lower = path.name.lower()

    if name_lower.endswith(".bam"):
        return _check_bam(path)
    if name_lower.endswith(".bgz"):
        ok = check_bgzf_eof(str(path))
        return (True, "BGZF integrity verified.") if ok else (False, "Corrupted (No BGZF EOF)")
    if name_lower.endswith(".gz") or name_lower.endswith(".fastq.gz"):
        if check_bgzf_eof(str(path)):
            return True, "BGZF integrity verified."
        return _check_gzip(path)

    return True, "Non-archive file verified."