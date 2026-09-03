import gzip
from pathlib import Path
import tarfile
from typing import Tuple
import zipfile


def verify_archive_integrity(file_path: Path) -> Tuple[bool, str]:
    """Sıkıştırılmış arşiv dosyalarının (gzip, zip, tar) iç bütünlüğünü,

    CRC checksum'larını ve dosya sonu (EOF) sağlamlığını doğrular.
    Bellek tasarrufu için dosyayı diske açmaz, akış üzerinden denetler.
    """
    path = Path(file_path)
    if not path.exists():
        return False, "Dosya bulunamadı."

    filename_lower = path.name.lower()

    try:
        # 1. Zip Dosyaları Denetimi
        if filename_lower.endswith(".zip"):
            with zipfile.ZipFile(path, "r") as zf:
                # testzip() arşivdeki bozuk ilk dosyanın adını döner, sağlamsa None döner
                bad_file = zf.testzip()
                if bad_file:
                    return False, f"Bozuk zip girdisi tespit edildi: {bad_file}"
            return True, "Zip arşivi ve CRC bütünlüğü doğrulandı."

        # 2. Tar / Tar.gz / Tgz Dosyaları Denetimi
        elif (
            filename_lower.endswith(".tar.gz")
            or filename_lower.endswith(".tgz")
            or filename_lower.endswith(".tar")
        ):
            mode = "r:*" if not filename_lower.endswith(".tar") else "r:"
            with tarfile.open(path, mode) as tf:
                # Tüm üye başlıklarını ve bloklarını oku
                for member in tf.getmembers():
                    if member.isfile():
                        f = tf.extractfile(member)
                        if f:
                            while f.read(1024 * 1024):
                                pass
            return True, "Tar arşivi blokları ve başlıkları doğrulandı."

        # 3. Gzip ve FASTQ.GZ Dosyaları Denetimi (Akış Bazlı CRC Kontrolü)
        elif filename_lower.endswith(".gz") or filename_lower.endswith(".fastq.gz") or filename_lower.endswith(".fq.gz"):
            # Gzip dosyasının sonundaki CRC32 ve ISIZE alanını doğrulamak için sonuna kadar akıt
            with gzip.open(path, "rb") as gz:
                chunk_size = 1024 * 1024  # 1 MB parça parça oku (RAM doldurmaz)
                while True:
                    data = gz.read(chunk_size)
                    if not data:
                        break
            return True, "Gzip/FASTQ akış CRC32 ve EOF bütünlüğü doğrulandı."

        else:
            # Sıkıştırılmamış dosyalar (csv, txt, pdf vb.) için arşiv testi atlanır
            return True, "Arşiv formatı değil (denetim atlandı)."

    except (gzip.BadGzipFile, zf_error := zipfile.BadZipFile, tarfile.TarError) as e:
        return False, f"Bozuk arşiv tespit edildi: {str(e)}"
    except EOFError:
        return False, "Eksik dosya sonu (Truncated/Kesik Arşiv)."
    except Exception as e:
        return False, f"Bütünlük denetiminde beklenmeyen hata: {str(e)}"