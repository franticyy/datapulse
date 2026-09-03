import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def generate_data_certificate(
    records: List[Dict[str, Any]],
    output_dir: str = "reports",
    manifest_name: str = "audit_manifest.json",
    html_name: str = "certificate.html",
) -> Dict[str, str]:
    """Generates immutable machine-readable JSON manifest and a modern HTML Data Certificate."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    manifest_file = out_path / manifest_name
    html_file = out_path / html_name
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. JSON Manifest
    manifest_data = {
        "metadata": {
            "engine": "DataPulse Resilient ETL",
            "version": "0.1.0",
            "generated_at": timestamp,
            "total_records": len(records),
        },
        "artifacts": records,
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4, ensure_ascii=False)

    # 2. Modern Dark-themed HTML Certificate
    table_rows = ""
    for r in records:
        status_color = "#10b981" if r.get("verified", False) else "#f59e0b"
        status_badge = "VERIFIED" if r.get("verified", False) else "PENDING / SKIPPED"

        table_rows += f"""
        <tr>
            <td style="font-family: monospace; color: #60a5fa;">{r.get('filename', 'N/A')}</td>
            <td>{r.get('size_bytes', 0):,} B</td>
            <td style="font-family: monospace; font-size: 0.85em; color: #9ca3af;">{r.get('calculated_md5', 'N/A')}</td>
            <td style="font-family: monospace; font-size: 0.85em; color: #9ca3af;">{r.get('calculated_sha256', 'N/A')[:16]}...</td>
            <td><span style="color: {status_color}; font-weight: bold; font-size: 0.85em; border: 1px solid {status_color}; padding: 2px 6px; border-radius: 4px;">{status_badge}</span></td>
            <td style="font-size: 0.85em; color: #d1d5db;">{r.get('archive_status', 'N/A')}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>DataPulse - Cryptographic Provenance Certificate</title>
    <style>
        body {{
            background-color: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            width: 100%;
            max-width: 1080px;
            background: #1e293b;
            border-radius: 12px;
            border: 1px solid #334155;
            padding: 32px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .header {{
            border-bottom: 1px solid #334155;
            padding-bottom: 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .title {{ font-size: 24px; font-weight: 700; color: #38bdf8; margin: 0; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            font-size: 14px;
        }}
        th, td {{
            text-align: left;
            padding: 12px 14px;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background-color: #0f172a;
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        tr:hover {{ background-color: #243247; }}
        .footer {{
            margin-top: 32px;
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #64748b;
            border-top: 1px solid #334155;
            padding-top: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1 class="title">⚡ DataPulse Verification Certificate</h1>
                <div class="subtitle">Cryptographic Data Provenance & Integrity Audit Trail</div>
            </div>
            <div style="text-align: right; font-size: 13px; color: #94a3b8;">
                <div>Engine: <strong>DataPulse v0.1.0</strong></div>
                <div>Timestamp: <strong>{timestamp}</strong></div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Artifact Name</th>
                    <th>Size</th>
                    <th>MD5 Checksum</th>
                    <th>SHA-256 (Prefix)</th>
                    <th>Status</th>
                    <th>Archive Integrity</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>

        <div class="footer">
            <div>Verified with zero-RAM streaming CRC32 inspection & cryptographic hashing.</div>
            <div>Provenance ID: <code style="color: #38bdf8;">{manifest_file.stem}</code></div>
        </div>
    </div>
</body>
</html>
"""
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    return {"json": str(manifest_file), "html": str(html_file)}