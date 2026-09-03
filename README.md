<div align="center">

# ⚡ DataPulse

**Enterprise-Grade Resilient Data Ingestion, Extraction & Cryptographic Provenance Engine**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

*A high-throughput, fault-tolerant ingestion pipeline designed for mission-critical datasets (e.g., NGS metagenomic FASTQ archives, open data repositories, release binaries) featuring zero-RAM archive inspection, dynamic worker pools, and automated cryptographic provenance audit trails.*

</div>

---

## 🎯 The Problem & Engineering Motivation

Modern automated data pipelines and data engineering workflows face recurring real-world failure modes:
1. **Network Instability & Flaky Servers:** Large transfers (1-20+ GB) frequently drop mid-stream, requiring redundant full-file redownloads without native HTTP range resume.
2. **Silent Bitrot & Truncated Archives:** Files can report a complete download (HTTP 200) despite containing network-induced bit flips, bad block headers, or missing EOF bytes (.fastq.gz, .tar.gz, .zip), which inevitably crashes downstream analytics pipelines hours later.
3. **Severe Upstream Bandwidth Throttling:** Specialized academic and government repositories (e.g., EBI/ENA Hinxton nodes) throttle single TCP streams down to ~400-800 KB/s.
4. **Lack of Data Provenance:** Production systems require verifiable proof regarding what was downloaded, when, from which origin, and under what cryptographic hash.

DataPulse solves these challenges out-of-the-box through an interactive, zero-configuration CLI workflow.

---

## 🏗 Key Features & Architecture

### 1. Zero-Friction Interactive Wizard (`datapulse auto`)
- Prompts only for the target URL and an optional search keyword.
- Automatically handles static HTML parsing (via BeautifulSoup) or switches dynamically to specialized REST APIs (e.g., ENA Portal API for genomic accessions PRJ*, ERR*, SRR*).
- Queries the user for desired concurrency (max_workers) to optimize network utilization.

### 2. Multi-Threaded Chunking & Resilient Streaming
- Built on httpx with HTTP/2 pooling and a 1 MB buffered zero-thrash I/O engine.
- Implements Range: bytes={offset}- headers to guarantee graceful auto-resume upon network interruption.
- Multi-bar visual monitoring powered by rich.progress.

### 3. Dual-Layer Cryptographic & Archive Integrity
- **Layer 1 (Checksum Matching):** Performs real-time MD5/SHA-256 calculation. If an authoritative checksum exists upstream, mismatches trigger autonomous file eviction and retry policies (Self-Healing).
- **Layer 2 (Zero-RAM Archive Verification):** Pipes gzip/FASTQ compressed streams directly to verify CRC32 and trailing ISIZE invariants, tests ZIP directory tables via zipfile.testzip(), and validates TAR block headers without unpacking files to disk.

### 4. Data Provenance & Cryptographic Audit Trails
- Compiles every pipeline execution into an immutable `reports/audit_manifest.json`.
- Automatically renders a modern, dark-themed HTML Data Certificate (`reports/certificate.html`) containing throughput metrics, file hashes, and compliance stamps.

---

## 🚀 Throughput Benchmarking

Observed real-world performance against bandwidth-throttled upstream servers (e.g., European Bioinformatics Institute):

| Ingestion Mode | Active Workers | Average Transfer Speed | Total Throughput | Fault Recovery |
| :--- | :---: | :---: | :---: | :---: |
| Standard Single Stream | 1 | ~380 kB/s | ~380 kB/s | None (Restart on drop) |
| DataPulse Parallel Pool | 4 | ~350 kB/s / worker | ~1.40 MB/s | Automatic Range Resume |
| DataPulse High-Concurrency | 8 | ~310 kB/s / worker | ~2.48 MB/s | Self-Healing + CRC32 |

*(When ingesting from CDNs or AWS S3 buckets, single-worker and multi-worker throughput readily saturates available local gigabit lines at 25-60+ MB/s).*

---

## 💻 Installation & Quickstart

```bash
# 1. Clone repository
git clone https://github.com/gulberkay/datapulse.git
cd datapulse

# 2. Setup virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install in editable mode with dependencies
pip install -e .
pip install "httpx[http2]"
```

---

## 🛠 Usage Examples

### 1. Interactive Auto-Pilot Wizard (Recommended)
```bash
datapulse auto
```

### 2. Standard Single-File Resilient Download
```bash
datapulse download "https://example.com/dataset.tar.gz" --output downloads
```

### 3. Cryptographic Verification
```bash
datapulse verify downloads/sample.fastq.gz <expected_hash> --algo md5
```

### 4. End-to-End Enterprise ETL Pipeline
```bash
datapulse pipeline --url "https://raw.githubusercontent.com/torvalds/linux/master/README"
```

---

## 📂 Generated Artifacts & Provenance

When an ingestion batch concludes, DataPulse writes immutable provenance records to reports/:
- `reports/audit_manifest.json` (Machine-readable provenance contract)
- `reports/certificate.html` (Verifiable, styled audit certificate)

---

## 🛡 License

This project is licensed under the MIT License - see the LICENSE file for details.