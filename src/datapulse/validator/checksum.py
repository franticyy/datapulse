import hashlib
import time


def calculate_hash(path: str, algorithm: str = "sha256") -> str:
    """Calculates cryptographic hash digest with a retry tolerance for file descriptor release."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            hasher = getattr(hashlib, algorithm)()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except PermissionError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.2)

    hasher = getattr(hashlib, algorithm)()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_checksum(file_path: str, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Compares calculated hash against an expected reference hash."""
    actual_hash = calculate_hash(file_path, algorithm=algorithm)
    return actual_hash.strip().lower() == expected_hash.strip().lower()