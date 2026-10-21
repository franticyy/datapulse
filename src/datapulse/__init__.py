"""
DataPulse — Resilient Genomic Data Engine
Logging konfigürasyonu burada merkezi olarak yapılır.
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(
    level: str = None,
    log_file: str = None,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
) -> None:
    """
    DataPulse için merkezi logging konfigürasyonu.

    Ortam değişkenleriyle kontrol edilebilir:
        DATAPULSE_LOG_LEVEL  — DEBUG / INFO / WARNING / ERROR (varsayılan: WARNING)
        DATAPULSE_LOG_FILE   — Log dosyası yolu (varsayılan: yok, sadece konsol)
    """
    log_level_str = (level or os.getenv("DATAPULSE_LOG_LEVEL", "WARNING")).upper()
    log_level = getattr(logging, log_level_str, logging.WARNING)
    log_file = log_file or os.getenv("DATAPULSE_LOG_FILE")

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    root_logger = logging.getLogger("datapulse")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    for noisy_lib in ("urllib3", "httplib2", "googleapiclient", "google"):
        logging.getLogger(noisy_lib).setLevel(logging.ERROR)


setup_logging()