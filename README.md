<div align="center">

# DataPulse

**Resilient, Provable Ingestion & Provenance Engine for Genomic Archives**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/franticyy/datapulse)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

---

## Overview

DataPulse is a lightweight, zero-configuration CLI tool and pipeline engine engineered to solve the chronic failure modes of high-throughput genomic data ingestion (ENA, SRA, NCBI). 

Rather than relying on unverified transfers or hammering public servers, DataPulse introduces:
- Ethical Mirror Routing: Transparent fallback to AWS Open Data public cloud buckets to bypass upstream bottlenecks and protect public infrastructure.
- Resilient Streaming: Chunked transfers powered by HTTP Range auto-resume.
- On-the-Fly Verification: Streamed CRC32 and archive boundary validation without high-memory decompression bottlenecks.
- Cryptographic Provenance: Automated creation of immutable audit manifests (JSON) and HTML Data Integrity Certificates.

---

## Architecture Flow

User Input (Accession / ENA URL / Direct Link)
                      │
                      ▼
       [ Smart Mirror Resolver ]
      /                         \
[AWS Open Data S3]       [Primary ENA Node]
(Zero Server Load)       (Graceful Fallback)
      \                         /
       ▼                       ▼
    [ Resilient HTTP Range Stream ]
                      │
                      ▼
     [ Real-Time Stream Decompressor ]
        ├── CRC32 Checksum Validation
        └── EOF / Truncation Sentinel
                      │
                      ▼
     [ Immutable Provenance Reporter ]
        ├── Machine-Readable JSON Manifest
        └── Human-Auditable HTML Certificate

---

## Key Features

- Ethical Cloud Routing (AWS Open Data): Parses ENA browser links or accession tags (ERR..., SRR...) and redirects payload streaming to AWS Open Data S3 mirrors (sra-pub-run-odp), eliminating public server stress and upstream rate-limiting.
- Fault-Tolerant Streaming: Seamlessly recovers interrupted connections byte-for-byte using standard HTTP Range headers.
- Streaming Archive Verification: Checks multi-gigabyte .fastq.gz archives on the fly for silent truncation (missing gzip EOF markers or bit rot) without saturating local RAM.
- Audit-Ready Certificates: Issues cryptographic audit records documenting SHA-256 digests, payload sizes, upstream resolution details, and integrity timestamps.
- Dual Mode (CLI & Auto-Pilot): Run targeted single downloads, parallel study batches, or launch interactive ingestion sessions.

---

## Installation

### From Source (Local Development)

git clone [https://github.com/franticyy/datapulse.git](https://github.com/franticyy/datapulse.git)
cd datapulse
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -e .

---

## Usage

### 1. Smart Download (Cloud Mirror Auto-Routing)

Pass a direct FASTQ URL, an ENA browser link, or a raw run accession ID. DataPulse automatically identifies the source and routes traffic to the optimal cloud mirror:

datapulse download "[https://www.ebi.ac.uk/ena/browser/view/ERR15003723](https://www.ebi.ac.uk/ena/browser/view/ERR15003723)"
datapulse download "ERR15003723"
datapulse download "[https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123456_1.fastq.gz](https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123456_1.fastq.gz)"

### 2. Full Ingestion Pipeline

Executes the complete lifecycle: Stream -> Hash Check -> Archive Validation -> Audit Manifest & Certificate:

datapulse pipeline "[https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123456_1.fastq.gz](https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123456_1.fastq.gz)" --output-dir ./data

### 3. Interactive Auto-Pilot Wizard

Launches an interactive prompt to resolve studies, configure thread concurrency, and execute multi-sample downloads:

datapulse auto

### 4. Standalone Integrity Check

Validate existing local files against silent corruption or truncated transfers:

datapulse verify-archive ./data/sample_1.fastq.gz

---

## Verification & Reports

Every completed pipeline run generates two artifacts in the reports/ directory:

1. audit_manifest.json: Machine-readable metadata record containing payload checksums, source provenance, and pipeline execution specs.
2. certificate.html: A self-contained, responsive report dashboard suitable for compliance auditing and publication supplementary documentation.

---

## Development & Testing

DataPulse maintains strict test coverage using pytest.

Run the test suite locally:

pytest -v

---

## License

Distributed under the MIT License. See LICENSE for more information.