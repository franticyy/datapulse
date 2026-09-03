from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError


class DataRecord(BaseModel):
    """Gelen verinin doğrulanacağı örnek şema modeli."""

    id: int = Field(..., description="Tekil kayıt kimliği")
    title: str = Field(..., min_length=2, description="Başlık veya ürün adı")
    category: str = Field(default="Genel")
    price: Optional[float] = Field(default=0.0, ge=0.0, description="Fiyat (negatif olamaz)")
    status: str = Field(default="active")


def validate_records(raw_data: List[Dict[str, Any]]) -> Tuple[List[DataRecord], List[Dict[str, Any]]]:
    """
    Gelen ham kayıtları doğrular.
    Geçerli kayıtları ve hatalı kayıtları (hata detayıyla birlikte) iki ayrı liste olarak döner.
    """
    valid_records: List[DataRecord] = []
    invalid_records: List[Dict[str, Any]] = []

    for item in raw_data:
        try:
            record = DataRecord(**item)
            valid_records.append(record)
        except ValidationError as e:
            invalid_records.append({"raw_item": item, "errors": e.errors()})

    return valid_records, invalid_records