from typing import Optional
import httpx


def send_webhook_notification(
    webhook_url: Optional[str],
    summary: dict,
    project_name: str = "DataPulse Pipeline",
) -> bool:
    """
    Discord / Slack uyumlu Webhook ile pipeline durumunu bildirir.
    Webhook URL verilmezse sessizce atlar veya konsola simüle eder.
    """
    if not webhook_url:
        return False

    status_icon = "✅" if summary.get("status") == "SUCCESS" else "⚠️"
    message_text = (
        f"{status_icon} **{project_name} Tamamlandı**\n"
        f"- Durum: `{summary.get('status')}`\n"
        f"- İndirilen Boyut: `{summary.get('downloaded_bytes', 0):,} bytes`\n"
        f"- Geçerli Kayıt: `{summary.get('valid_records', 0)}`\n"
        f"- Hatalı Kayıt: `{summary.get('invalid_records', 0)}`\n"
        f"- Checksum Bütünlüğü: `{summary.get('checksum_verified')}`"
    )

    payload = {"content": message_text}

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        return response.status_code in (200, 204)
    except Exception:
        return False