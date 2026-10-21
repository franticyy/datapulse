import hashlib


CHUNK_SIZE = 1024 * 1024  # 1 MB


def calculate_hash(filepath: str, algorithm: str = "md5") -> str:
    algorithm = algorithm.lower().replace("-", "")

    if algorithm == "md5":
        hasher = hashlib.md5()
    elif algorithm in ("sha256", "sha_256"):
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Desteklenmeyen algoritma: {algorithm}. 'md5' veya 'sha256' kullanın.")

    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return "ERROR"


def verify_checksum(filepath: str, expected: str, algorithm: str = "md5") -> bool:
    calculated = calculate_hash(filepath, algorithm)
    if calculated == "ERROR":
        return False
    return calculated.lower() == expected.lower()