import hashlib
from pathlib import Path


def calculate_hash(
    file_path: Path | str, algorithm: str = "sha256", chunk_size: int = 1024 * 64
) -> str:
    """Büyük dosyaları bellek dostu şekilde parça parça okuyarak hash hesaplar."""
    algo = algorithm.lower()
    if algo == "md5":
        hasher = hashlib.md5()
    elif algo == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Desteklenmeyen algoritma: {algorithm}. 'md5' veya 'sha256' kullanın.")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")

    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def verify_checksum(
    file_path: Path | str, expected_hash: str, algorithm: str = "sha256"
) -> bool:
    """Hesaplanan hash ile beklenen hash değerini güvenli şekilde karşılaştırır."""
    calculated = calculate_hash(file_path, algorithm=algorithm)
    # Timing attack riskini önlemek için hmac.compare_digest benzeri güvenli karşılaştırma
    import hmac

    return hmac.compare_digest(calculated.lower(), expected_hash.strip().lower())