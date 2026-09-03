from datapulse.validator.schema import DataRecord
from datapulse.reporter.exporter import export_to_excel, generate_pipeline_summary
from datapulse.reporter.notifier import send_webhook_notification

# Örnek doğrulanmış kayıtlar
sample_records = [
    DataRecord(id=1, title="Mekanik Klavye", category="Donanım", price=1250.0),
    DataRecord(id=2, title="Oyuncu Faresi", category="Donanım", price=650.0),
    DataRecord(id=3, title="Tip-C Kablo", category="Aksesuar", price=120.0),
]

# 1. Excel raporunu oluştur
report_path = export_to_excel(sample_records)
print(f"Excel Raporu Oluşturuldu: {report_path}")

# 2. Özet metrik çıkar
summary = generate_pipeline_summary(
    total_downloaded_bytes=2048,
    valid_count=len(sample_records),
    invalid_count=0,
    checksum_passed=True,
)
print(f"Pipeline Özeti: {summary}")

# 3. Webhook simülasyonu (URL olmadığı için güvenli şekilde atlar)
sent = send_webhook_notification(webhook_url=None, summary=summary)
print(f"Webhook Bildirimi Gönderildi mi: {sent} (URL tanımlanmadığı için pas geçildi)")