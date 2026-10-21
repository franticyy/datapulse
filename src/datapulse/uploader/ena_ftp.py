import logging
from ftplib import FTP, FTP_TLS, error_perm, error_temp
from pathlib import Path

logger = logging.getLogger(__name__)


def upload_ena_ftp(
    file_path: str,
    username: str,
    password: str,
    server: str = "webin.ebi.ac.uk",
    port: int = 21,
    progress=None,
    task_id=None,
    chunk_size: int = 65536,
) -> bool:
    """
    ENA Webin Dropoff'a FTP veya FTPS ile dosya yükler.
    Önce düz FTP dener; bağlantı/kimlik doğrulama hatası alırsa FTPS'e geçer.

    Raises:
        FileNotFoundError: Dosya yoksa
        PermissionError: Kimlik doğrulama başarısızsa (her iki protokolde de)
        RuntimeError: Diğer FTP hataları
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")

    def _make_callback():
        def _callback(block):
            if progress and task_id is not None:
                progress.update(task_id, advance=len(block))
        return _callback

    # --- 1. Düz FTP denemesi ---
    try:
        logger.debug("ENA FTP bağlantısı deneniyor: %s:%d", server, port)
        ftp = FTP()
        ftp.connect(host=server, port=port, timeout=60)
        ftp.login(user=username, passwd=password)
        ftp.set_pasv(True)

        with open(path, "rb") as f:
            ftp.storbinary(f"STOR {path.name}", f, blocksize=chunk_size, callback=_make_callback())

        try:
            ftp.quit()
        except Exception:
            ftp.close()

        logger.info("FTP yükleme başarılı: %s", path.name)
        return True

    except error_perm as e:
        logger.warning("FTP kimlik doğrulama hatası: %s — FTPS deneniyor.", e)
    except error_temp as e:
        logger.warning("FTP geçici hata: %s — FTPS deneniyor.", e)
    except OSError as e:
        logger.warning("FTP bağlantı hatası: %s — FTPS deneniyor.", e)

    # --- 2. FTPS (TLS) denemesi ---
    try:
        logger.debug("ENA FTPS bağlantısı deneniyor: %s:%d", server, port)
        ftps = FTP_TLS()
        ftps.connect(host=server, port=port, timeout=60)
        ftps.auth()
        ftps.login(user=username, passwd=password)
        ftps.prot_p()
        ftps.set_pasv(True)

        with open(path, "rb") as f:
            ftps.storbinary(f"STOR {path.name}", f, blocksize=chunk_size, callback=_make_callback())

        try:
            ftps.quit()
        except Exception:
            ftps.close()

        logger.info("FTPS yükleme başarılı: %s", path.name)
        return True

    except error_perm as e:
        raise PermissionError(f"ENA kimlik doğrulama başarısız (FTP ve FTPS): {e}") from e
    except OSError as e:
        raise RuntimeError(f"ENA FTPS bağlantı hatası: {e}") from e