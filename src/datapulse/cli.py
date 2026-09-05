import os
import sys
import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import click
import requests
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    SpinnerColumn
)

from datapulse.downloader.stream import download_stream
from datapulse.downloader.mirror import resolve_optimal_mirror
from datapulse.downloader.parallel import download_concurrently
from datapulse.scraper.nextcloud import list_nextcloud_files, parse_nextcloud_share_url
from datapulse.scraper.extractor import fetch_ena_links
from datapulse.scraper.gdrive import (
    parse_gdrive_url, 
    list_gdrive_folder_files, 
    get_gdrive_direct_download_info
)
from datapulse.validator.archive import verify_archive_integrity
from datapulse.validator.checksum import calculate_hash
from datapulse.reporter.certificate import generate_data_certificate
from datapulse.reporter.exporter import generate_pipeline_summary
from datapulse.reporter.notifier import send_webhook_notification

console = Console()


def is_genomic_accession(val: str) -> bool:
    """NCBI / ENA accession formatini dogrular."""
    pattern = r"^[A-Z]{3,6}\d{5,9}$"
    return bool(re.match(pattern, val.strip().upper()))


def _safe_remove(file_path: Path, retries: int = 5, delay: float = 0.5):
    """Windows uzerindeki dosya kilitlerini (WinError 32) asarak guvenli silme yapar."""
    for _ in range(retries):
        try:
            if file_path.exists():
                file_path.unlink()
            return
        except (PermissionError, OSError):
            time.sleep(delay)


def _fetch_remote_md5_content(url: str) -> str:
    """Nextcloud veya HTTP uzerindeki .md5/.md5sum dosyasinin icindeki hash'i ceker."""
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            text = r.text.strip()
            match = re.search(r"([a-fA-F0-9]{32})", text)
            if match:
                return match.group(1).lower()
    except Exception:
        pass
    return None


def _process_single_target(
    target: dict, 
    output_dir: str, 
    progress: Progress, 
    task_id, 
    webhook: str = None,
    max_retries: int = 3
) -> dict:
    """Dosyayi indirir, MD5/SHA256 ve EOF testlerini yapar. Bozuksa guvenli silip bastan dener."""
    out_path = Path(output_dir) / target["filename"]
    expected_md5 = target.get("expected_md5")

    for attempt in range(1, max_retries + 1):
        progress.update(task_id, description=f"[cyan]{target['filename'][:20]} ({attempt}/{max_retries})[/cyan]")
        download_stream(
            target["stream_url"], 
            str(out_path), 
            progress=progress, 
            task_id=task_id
        )

        progress.update(task_id, description=f"[yellow]Doğrulanıyor: {target['filename'][:15]}...[/yellow]")

        file_sha256 = calculate_hash(str(out_path), algorithm="sha256")
        file_md5 = calculate_hash(str(out_path), algorithm="md5")

        md5_match = True
        if expected_md5:
            md5_match = (file_md5.lower() == expected_md5.lower())

        archive_valid = True
        archive_status = "Not Compressed"
        if str(out_path).endswith((".gz", ".fastq.gz", ".tar.gz", ".zip", ".fq.gz")):
            archive_res = verify_archive_integrity(str(out_path))
            if isinstance(archive_res, tuple):
                archive_valid, archive_status = archive_res
            else:
                archive_valid = bool(archive_res)
                archive_status = "Valid" if archive_valid else "Corrupted"

        is_fully_healthy = md5_match and archive_valid

        if is_fully_healthy:
            status_text = "MD5 OK | EOF OK" if expected_md5 else f"EOF {archive_status}"
            progress.update(task_id, description=f"[green]✓ {target['filename'][:20]} ({status_text})[/green]")
            
            audit_data = {
                "source_input": target["source_input"],
                "resolved_url": target["stream_url"],
                "provider": target["provider"],
                "output_file": str(out_path),
                "file_size": os.path.getsize(out_path),
                "sha256": file_sha256,
                "md5": file_md5,
                "expected_md5": expected_md5 or "N/A",
                "md5_matched": md5_match,
                "archive_valid": archive_valid,
                "archive_status": archive_status,
                "attempts": attempt
            }

            clean_name = Path(target["filename"]).stem.replace(".", "_")
            cert_path = f"./reports/certificate_{clean_name}.html"
            try:
                generate_data_certificate(audit_data, cert_path)
            except Exception:
                pass

            if webhook:
                send_webhook_notification(webhook, audit_data)

            return audit_data
        else:
            fail_reason = "MD5 Uyuşmazlığı" if not md5_match else f"Bozuk Arşiv ({archive_status})"
            if attempt < max_retries:
                progress.update(task_id, description=f"[red]✗ Hatalı ({fail_reason})! Tekrar deneniyor...[/red]")
                _safe_remove(out_path)
                for part_file in Path(output_dir).glob(f"{target['filename']}*.part"):
                    _safe_remove(part_file)
                time.sleep(1)
            else:
                progress.update(task_id, description=f"[bold red]✗ {target['filename'][:15]} doğrulanamadı![/bold red]")
                return {
                    "source_input": target["source_input"],
                    "resolved_url": target["stream_url"],
                    "provider": target["provider"],
                    "output_file": str(out_path),
                    "file_size": os.path.getsize(out_path) if os.path.exists(out_path) else 0,
                    "sha256": file_sha256,
                    "md5": file_md5,
                    "expected_md5": expected_md5 or "N/A",
                    "md5_matched": md5_match,
                    "archive_valid": archive_valid,
                    "archive_status": f"FAILED ({fail_reason})",
                    "attempts": attempt
                }


@click.group(invoke_without_command=True)
@click.pass_context
def app(ctx):
    """DataPulse: Resilient, Provable Ingestion & Provenance Engine for Genomic Archives."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(pipeline)


@app.command()
@click.option("--url", "-u", default=None, help="Accession kodu, Cloud linki veya dosya URL'si.")
@click.option("--output-dir", "-o", default="./downloads", help="Hedef klasor.")
@click.option("--filter", "-f", "filter_keyword", default=None, help="Dosya veya metadata filtre kelimesi.")
@click.option("--workers", "-w", default=None, type=int, help="Eszamanli indirme is parcacigi sayisi.")
@click.option("--webhook", default=None, help="Discord/Slack Webhook bildirim URL'si.")
def pipeline(url: str, output_dir: str, filter_keyword: str, workers: int, webhook: str):
    """Interaktif, coklu kaynak destekli, filtrelemeli ve self-healing pipeline calistiricisi."""
    console.print(
        Panel.fit(
            "[bold cyan]DataPulse Self-Healing Genomic Pipeline[/bold cyan]\n"
            "[dim]NCBI/ENA • Nextcloud • Google Drive • Canlı Hız Panosu • MD5/EOF Testi • Auto-Retry[/dim]",
            border_style="cyan",
        )
    )

    # 1. URL / Kod Istegi
    if not url:
        url = Prompt.ask("\n[bold yellow]👉 Lütfen NCBI/ENA Proje Kodu, FASTQ URL'si veya Cloud Linkini (Nextcloud / Google Drive) girin[/bold yellow]")

    url = url.strip()
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("./reports", exist_ok=True)

    raw_targets = []
    base_nc, token_nc = parse_nextcloud_share_url(url)
    gdrive_type, gdrive_id = parse_gdrive_url(url)

    # 2. Kaynak Tespiti
    # Durum A: Google Drive Klasörü
    if gdrive_type == "folder":
        console.print(f"\n[bold cyan]🔍 Kaynak: Google Drive Klasörü Tespit Edildi ({gdrive_id})[/bold cyan]")
        console.print("[dim]Google Drive klasör içeriği taranıyor...[/dim]")
        g_files = list_gdrive_folder_files(url)
        
        if not g_files:
            console.print("[yellow]Uyarı: Klasör listeleyici yanıt vermedi, doğrudan gdown ile senkronize ediliyor...[/yellow]")
            import gdown
            gdown.download_folder(url=url, output=output_dir, quiet=False)
            console.print("[bold green]✓ Klasördeki dosyalar indirildi![/bold green]")
            return

        for f in g_files:
            raw_targets.append({
                "stream_url": f["stream_url"] or f"https://drive.google.com/uc?id={f['file_id']}&export=download",
                "provider": "Google Drive Cloud Engine",
                "filename": f["filename"],
                "source_input": url,
                "expected_md5": None,
                "meta_text": f["filename"]
            })

    # Durum B: Google Drive Tekil Dosyası
    elif gdrive_type == "file":
        console.print(f"\n[bold cyan]🔍 Kaynak: Google Drive Tekil Dosyası Tespit Edildi ({gdrive_id})[/bold cyan]")
        direct_url, fname = get_gdrive_direct_download_info(gdrive_id)
        raw_targets.append({
            "stream_url": direct_url,
            "provider": "Google Drive Cloud Engine",
            "filename": fname,
            "source_input": url,
            "expected_md5": None,
            "meta_text": fname
        })

    # Durum C: Nextcloud / ownCloud Paylaşımı
    elif "index.php/s/" in url or base_nc:
        console.print(f"\n[bold cyan]🔍 Kaynak: Nextcloud Klasörü Tespit Edildi[/bold cyan]")
        console.print("[dim]Klasör içeriği taranıyor...[/dim]")
        files = list_nextcloud_files(url)
        if not files:
            console.print("[red]✗ Paylaşılan klasör boş veya erişilemiyor.[/red]")
            sys.exit(1)

        md5_map = {}
        for f in files:
            fname = f["filename"]
            if fname.endswith((".md5", ".md5sum")):
                target_base = re.sub(r"\.(md5|md5sum)$", "", fname)
                md5_val = _fetch_remote_md5_content(f["url"])
                if md5_val:
                    md5_map[target_base] = md5_val

        for f in files:
            raw_targets.append({
                "stream_url": f["url"],
                "provider": "Nextcloud WebDAV Mirror",
                "filename": f["filename"],
                "source_input": url,
                "expected_md5": md5_map.get(f["filename"]),
                "meta_text": f["filename"]
            })

    # Durum D: NCBI / ENA Accession Kodu (PRJNA..., PRJEB..., SRP..., SRR...)
    elif is_genomic_accession(url):
        console.print(f"\n[bold cyan]🧬 Kaynak: NCBI / ENA Accession ({url.upper()})[/bold cyan]")
        console.print("[dim]ENA Portal API üzerinden kayıtlar ve ayna hatları taranıyor...[/dim]")
        ena_records = fetch_ena_links(url.strip())
        if not ena_records:
            console.print(f"[red]✗ {url} koduna ait FASTQ kaydı bulunamadı.[/red]")
            sys.exit(1)

        for rec in ena_records:
            raw_url = rec.get("fastq_url") or rec.get("url")
            fname = rec.get("filename") or Path(raw_url.split("?")[0]).name
            optimal_url, optimal_provider = resolve_optimal_mirror(raw_url)
            
            meta_str = (
                f"{fname} "
                f"{rec.get('run_accession', '')} "
                f"{rec.get('sample_accession', '')} "
                f"{rec.get('scientific_name', '')} "
                f"{rec.get('sample_title', '')} "
                f"{rec.get('experiment_title', '')}"
            )

            raw_targets.append({
                "stream_url": optimal_url,
                "provider": optimal_provider,
                "filename": fname,
                "source_input": url,
                "expected_md5": rec.get("fastq_md5") or rec.get("md5"),
                "meta_text": meta_str
            })

    # Durum E: Doğrudan URL / Akış
    else:
        stream_url, provider = resolve_optimal_mirror(url)
        filename = Path(stream_url.split("?")[0]).name
        if not filename or filename == "download":
            filename = "sample.fastq.gz" if "fastq" in url else "stream_output.dat"

        raw_targets.append({
            "stream_url": stream_url,
            "provider": provider,
            "filename": filename,
            "source_input": url,
            "expected_md5": None,
            "meta_text": filename
        })

    console.print(f"[green]✓ Kaynaktan toplam {len(raw_targets)} adet dosya kaydı bulundu.[/green]")

    # 3. Spesifik Kelime Filtresi
    if filter_keyword is None and len(raw_targets) > 1:
        filter_keyword = Prompt.ask(
            "[bold yellow]👉 İndirmek istediğin özel bir kelime/filtre var mı? (Örn: 'human oral metagenome', '_1', 'control' - Hepsini indirmek için Enter'a bas)[/bold yellow]",
            default=""
        )

    targets = []
    if filter_keyword and filter_keyword.strip():
        term = filter_keyword.strip().lower()
        for t in raw_targets:
            if term in t["meta_text"].lower():
                targets.append(t)
        console.print(f"[bold cyan]🔍 Filtre uygulandı ('{term}'): {len(targets)}/{len(raw_targets)} dosya eşleşti.[/bold cyan]")
        if not targets:
            console.print("[red]✗ Aranan kelimeye uygun dosya bulunamadı.[/red]")
            sys.exit(0)
    else:
        targets = raw_targets

    # 4. Worker Sayısı
    total_files = len(targets)
    if workers is None:
        workers = IntPrompt.ask(
            "[bold yellow]👉 Aynı anda kaç dosya indirilsin? (Eşzamanlı worker sayısı)[/bold yellow]",
            default=min(6, total_files) if total_files > 0 else 4,
        )

    console.print(
        f"\n[bold green]⚡ {workers} worker ile paralel indirme, doğrulama ve auto-retry başlatılıyor...[/bold green]\n"
    )

    all_audits = []

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="left"),
        BarColumn(bar_width=25),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console
    )

    with progress:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for target in targets:
                t_id = progress.add_task(f"[cyan]{target['filename'][:20]}[/cyan]", total=None)
                fut = executor.submit(
                    _process_single_target, 
                    target, 
                    output_dir, 
                    progress, 
                    t_id, 
                    webhook,
                    3
                )
                futures[fut] = target

            for future in as_completed(futures):
                try:
                    res = future.result()
                    all_audits.append(res)
                except Exception as e:
                    failed_file = futures[future]["filename"]
                    console.print(f"[bold red]✗ {failed_file} işlenirken hata oluştu: {e}[/bold red]")

    # 5. Raporlama
    manifest_path = "./reports/audit_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            all_audits if len(all_audits) > 1 else (all_audits[0] if all_audits else {}),
            f,
            indent=2,
        )

    try:
        generate_pipeline_summary(all_audits, "./reports/pipeline_summary.xlsx")
    except Exception:
        pass

    console.print(
        f"\n[bold green]✓ İşlem tamamlandı! Toplam {len(all_audits)}/{len(targets)} dosya denetlendi.[/bold green]"
    )
    console.print("[dim]Raporlar ./reports/ klasörüne kaydedildi.[/dim]")


@app.command()
@click.argument("archive_path")
def verify_archive(archive_path: str):
    """Mevcut yerel FASTQ/Gzip arşivlerinin bütünlük ve EOF durumunu test eder."""
    if not os.path.exists(archive_path):
        console.print(f"[red]Hata: {archive_path} dosyası bulunamadı.[/red]")
        sys.exit(1)

    console.print(f"[yellow]{archive_path} için arşiv sınırları ve EOF sentineli taranıyor...[/yellow]")
    archive_res = verify_archive_integrity(archive_path)
    is_valid = archive_res[0] if isinstance(archive_res, tuple) else bool(archive_res)

    if is_valid:
        console.print("[bold green]✓ Arşiv bütünlüğü doğrulandı (EOF sentineli geçerli).[/bold green]")
    else:
        console.print("[bold red]✗ Arşiv bozuk veya eksik (truncated)![/bold red]")


cli = app

if __name__ == "__main__":
    app()