from typing import Optional
from pydantic import BaseModel, Field


class DataRecord(BaseModel):
    """
    İndirilen ve doğrulanan bir veri dosyasını temsil eder.
    exporter.py tarafından Excel raporuna dönüştürülür.
    """

    # Dosya kimliği
    filename: str = Field(..., description="Dosya adı")
    path: Optional[str] = Field(None, description="Yerel disk yolu")

    # Boyut
    size_bytes: int = Field(0, description="Dosya boyutu (bayt)")

    # Checksum
    calculated_md5: Optional[str] = Field(None, description="Hesaplanan MD5")
    calculated_sha256: Optional[str] = Field(None, description="Hesaplanan SHA-256")

    # Doğrulama sonucu
    verified: bool = Field(False, description="Hash ve arşiv bütünlüğü geçti mi?")
    archive_status: Optional[str] = Field(None, description="Arşiv bütünlük mesajı")
    status: Optional[str] = Field(None, description="VERIFIED / FAILED / ERROR")

    # Kaynak bilgisi
    source_url: Optional[str] = Field(None, description="İndirme URL'si")
    mirror_provider: Optional[str] = Field(None, description="Kullanılan mirror (AWS, EBI...)")

    # ENA metadata
    run_accession: Optional[str] = None
    sample_accession: Optional[str] = None
    study_accession: Optional[str] = None
    scientific_name: Optional[str] = None

    # Hata
    error: Optional[str] = Field(None, description="Varsa hata mesajı")

    model_config = {"extra": "allow"}  # cli.py'den gelen ek alanları kabul et