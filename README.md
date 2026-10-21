<div align="center">

# DataPulse

**Resilient, Provable Ingestion & Provenance Engine for Genomic Archives**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-47%20passed-brightgreen.svg)](https://github.com/franticyy/datapulse)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

---

## Overview

DataPulse is a lightweight, zero-configuration CLI tool and pipeline engine engineered to solve the chronic failure modes of high-throughput genomic data ingestion (ENA, SRA, NCBI).

Rather than relying on unverified transfers or hammering public servers, DataPulse introduces:

- **Ethical Mirror Routing** — Transparent fallback to AWS Open Data public cloud buckets to bypass upstream bottlenecks and protect public infrastructure.
- **Resilient Streaming** — Chunked transfers powered by HTTP Range auto-resume; interrupted downloads continue byte-for-byte from where they left off.
- **On-the-Fly Verification** — Streamed CRC32 and BGZF archive boundary validation without high-memory decompression bottlenecks.
- **Cryptographic Provenance** — Automated creation of immutable audit manifests (JSON) and HTML Data Integrity Certificates with MD5 + SHA-256 digests.
- **Multi-Cloud Upload** — Push verified files to Nextcloud, AWS S3/MinIO, ENA Webin FTP, or Google Drive from a single CLI prompt.

---

## Architecture

\```
User Input (Accession ID / ENA URL / GDrive / Nextcloud)
                      │
                      ▼
         [ Source Resolver ]
         ├── ENA Portal API  (ERR / SRR / PRJ / SAMN)
         ├── Google Drive    (drive.google.com links)
         └── Nextcloud       (WebDAV public share)
                      │
                      ▼
       [ Smart Mirror Resolver ]
      ┌───────────────────────────┐
      │  1. AWS Open Data S3      │  ← tried first (fastest)
      │  2. EBI HTTPS Mirror      │  ← fallback
      │  3. EBI FTP               │  ← last resort
      └───────────────────────────┘
                      │
                      ▼
    [ Resilient HTTP Range Stream ]
          (auto-resume on failure)
                      │
                      ▼
     [ Validator ]
        ├── MD5 / SHA-256 checksum
        ├── BGZF EOF sentinel check  (.bam / .fastq.gz)
        └── Gzip CRC32 integrity
                      │
                      ▼
     [ Provenance Reporter ]
        ├── audit_manifest.json
        └── certificate.html
                      │
                      ▼
     [ Multi-Cloud Uploader ]  (optional)
        ├── Nextcloud WebDAV
        ├── AWS S3 / MinIO
        ├── ENA Webin FTP/FTPS
        └── Google Drive (resumable)
\```

---

## Project Structure

\```
src/datapulse/
├── cli.py
├── downloader/
│   ├── stream.py
│   ├── parallel.py
│   └── mirror.py
├── scraper/
│   ├── extractor.py
│   ├── gdrive.py
│   └── nextcloud.py
├── validator/
│   ├── checksum.py
│   ├── archive.py
│   └── schema.py
├── reporter/
│   ├── certificate.py
│   ├── exporter.py
│   └── notifier.py
└── uploader/
    ├── nextcloud.py
    ├── s3.py
    ├── ena_ftp.py
    └── gdrive.py
\```

---

## Installation

\```bash
git clone https://github.com/franticyy/datapulse.git
cd datapulse
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\Activate.ps1       # Windows PowerShell
pip install -e .
\```

---

## Usage

### Download Modu

\```bash
datapulse
# → "1: Download" seçin
\```

Desteklenen kaynaklar: ENA/SRA accession ID, Google Drive klasör linki, Nextcloud paylaşım linki.

### Upload Modu

\```bash
datapulse
# → "2: Upload" seçin
\```

Hedefler: Nextcloud, AWS S3/MinIO, ENA Webin FTP/FTPS, Google Drive.

---

## Development & Testing

\```bash
python -m pytest tests/ -v
\```

| Test Dosyası | Kapsam | Test Sayısı |
|---|---|---|
| `test_pipeline.py` | Checksum, Archive, Certificate, Mirror | 4 |
| `test_uploaders.py` | Nextcloud, S3, ENA FTP, GDrive | 20 |
| `test_downloaders.py` | Stream, Mirror, Parallel worker | 23 |
| **Toplam** | | **47** |

---

## License

Distributed under the MIT License.