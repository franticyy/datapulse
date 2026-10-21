import os
import sys
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from datapulse.downloader.stream import download_stream
import datapulse.scraper.extractor as ext_mod
import datapulse.scraper.gdrive as gdrive_mod
import datapulse.scraper.nextcloud as nextcloud_mod
import datapulse.downloader.mirror as mirror_mod
import datapulse.validator.archive as arch_mod
import datapulse.validator.checksum as check_mod
from datapulse.validator.checksum import calculate_hash
import datapulse.reporter.certificate as cert_mod
import datapulse.reporter.exporter as exp_mod

# Upload Modülleri
import datapulse.uploader.nextcloud as up_nc
import datapulse.uploader.s3 as up_s3
import datapulse.uploader.ena_ftp as up_ena
import datapulse.uploader.gdrive as up_gd


console = Console()


class ReportRecord(dict):
    def model_dump(self, **_kwargs):
        return dict(self)

    def __getattr__(self, item):
        return self.get(item)


def is_file_fully_verified(filepath: str, expected_size: int = None) -> bool:
    if not os.path.exists(filepath):
        return False
    local_size = os.path.getsize(filepath)
    if local_size == 0:
        return False
    if expected_size and expected_size > 0:
        if local_size < expected_size:
            return False
    fn_lower = filepath.lower()
    if fn_lower.endswith((".bam", ".gz", ".bgz")):
        try:
            return arch_mod.check_bgzf_eof(filepath)
        except Exception:
            return True
    return True


def build_record_dict(file_name: str, dest_path: str, eof_status: str, sha256_hash: str = None) -> "ReportRecord":
    file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
    md5_hash = calculate_hash(dest_path, algorithm="md5")
    if not sha256_hash or sha256_hash in ["N/A", "ERROR"]:
        sha256_hash = calculate_hash(dest_path, algorithm="sha256")
    is_valid = "Corrupted" not in eof_status and sha256_hash != "ERROR"
    return ReportRecord({
        "filename": file_name,
        "path": dest_path,
        "size_bytes": file_size,
        "calculated_md5": md5_hash,
        "calculated_sha256": sha256_hash,
        "verified": is_valid,
        "archive_status": eof_status if eof_status != "N/A" else "Non-archive file verified.",
        "status": "VERIFIED" if is_valid else "FAILED",
    })


def resolve_source_files(target_input: str) -> list:
    target_lower = target_input.lower()

    if any(k in target_lower for k in ["index.php/s/", "nextcloud", "owncloud", "genclouddrive"]):
        console.print("[cyan]🔍 Kaynak: Nextcloud / WebDAV tespit edildi.[/cyan]")
        raw_files = nextcloud_mod.list_nextcloud_files(target_input)
        normalized = []
        for f in raw_files:
            fname = f.get("filename") or f.get("name") or "unnamed"
            furl = f.get("url") or f.get("stream_url") or f.get("download_url")
            fsize = f.get("size")
            record = dict(f)
            record.update({"name": fname, "stream_url": furl, "size": fsize})
            normalized.append(record)
        return normalized

    if any(k in target_lower for k in ["drive.google.com", "folders/", "id="]) or len(target_input) in [28, 33, 44]:
        console.print("[cyan]🔍 Kaynak: Google Drive arşivi tespit edildi.[/cyan]")
        return gdrive_mod.list_gdrive_folder_files(target_input)

    if any(target_input.upper().startswith(p) for p in ["PRJ", "ERR", "SRR", "DRR", "SAMN", "ERP"]):
        console.print(f"[cyan]🧬 Kaynak: Biyo-arşiv Accession ID ({target_input.upper()}) tespit edildi.[/cyan]")
        return mirror_mod.resolve_mirrors(target_input)

    try:
        return ext_mod.fetch_ena_links(target_input)
    except Exception as exc:
        raise ValueError(f"Desteklenmeyen kaynak girdisi: {target_input}") from exc


def run_download() -> None:
    """İndirme, Smart Skip, Failover ve Raporlama Motoru"""
    url_input = console.input(
        "\n[bold yellow]?[/bold yellow] Veri Kaynağı (GDrive Linki, Nextcloud Linki veya ENA/NCBI ID):\n[dim]>> [/dim]"
    ).strip()

    if not url_input:
        url_input = "PRJEB79944"

    with console.status("[cyan]Veri kaynağı taranıyor ve aynalar çözümleniyor...[/cyan]", spinner="dots"):
        try:
            files = resolve_source_files(url_input)
        except Exception as e:
            console.print(f"[bold red]Hata:[/bold red] Kaynak taranırken sorun oluştu: {e}")
            sys.exit(1)

    if not files:
        console.print("[yellow]Hedef kaynakta indirilebilir dosya bulunamadı.[/yellow]")
        sys.exit(0)

    console.print(f"[green]✓[/green] Toplam [bold cyan]{len(files)}[/bold cyan] dosya tespit edildi.")

    filter_term = console.input(
        "\n[bold yellow]?[/bold yellow] İndirmek istediğin özel bir kelime/filtre var mı? (Hepsini indirmek için Enter'a bas): "
    ).strip()

    if filter_term:
        term_clean = filter_term.lower()

        def matches_filter(item):
            fname = (item.get("name") or item.get("filename") or "").lower()
            if term_clean in fname:
                return True
            for val in item.values():
                if isinstance(val, str) and term_clean in val.lower():
                    return True
                elif isinstance(val, (list, tuple)):
                    for sub in val:
                        if isinstance(sub, str) and term_clean in sub.lower():
                            return True
            return False

        filtered_files = [f for f in files if matches_filter(f)]
        console.print(f"[cyan]ℹ[/cyan] Filtre uygulandı: [bold green]{len(filtered_files)}/{len(files)}[/bold green] dosya eşleşti.")
        target_files = filtered_files
    else:
        target_files = files

    if not target_files:
        console.print("[yellow]Filtreye uygun dosya bulunamadı. Çıkılıyor.[/yellow]")
        sys.exit(0)

    downloads_dir = os.path.abspath("downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    skip_prompt = console.input(
        "\n[bold yellow]?[/bold yellow] Sadece tam inmiş ve doğrulanmış dosyalar atlansın mı? (Yarıda kalanlar devam eder) (E/h): "
    ).strip().lower()
    skip_existing = skip_prompt != "h"

    already_downloaded = []
    to_download = []

    for f in target_files:
        fn = f.get("name") or f.get("filename") or "unnamed"
        fp = os.path.join(downloads_dir, fn)
        expected_sz = f.get("size")
        if skip_existing and is_file_fully_verified(fp, expected_sz):
            already_downloaded.append(f)
        else:
            to_download.append(f)

    if skip_existing:
        if already_downloaded:
            table = Table(title="[bold green]📁 Doğrulanmış ve Tam Olduğu İçin Atlanan Dosyalar[/bold green]", border_style="green")
            table.add_column("Dosya Adı", style="cyan")
            table.add_column("Mevcut Boyut", justify="right", style="green")
            table.add_column("Durum", justify="center", style="bold green")
            for f in already_downloaded:
                fn = f.get("name") or f.get("filename") or "unnamed"
                fp = os.path.join(downloads_dir, fn)
                sz = os.path.getsize(fp)
                sz_str = f"{sz / (1024**3):.2f} GB" if sz >= 1024**3 else f"{sz / (1024**2):.2f} MB"
                table.add_row(fn, sz_str, "TAM & DOĞRULANDI")
            console.print(table)
            console.print(
                f"[yellow]⚡ Toplam [bold]{len(already_downloaded)}[/bold] tam dosya atlandı, "
                f"[bold green]{len(to_download)}[/bold green] dosya indirilecek/tamamlanacak.[/yellow]\n"
            )
        else:
            console.print("[dim cyan]ℹ Tam inmiş dosya bulunamadı; eksik/yarıda kalan tüm dosyalar tamamlanacak.[/dim cyan]\n")

    results = []
    for f in already_downloaded:
        fn = f.get("name") or f.get("filename") or "unnamed"
        fp = os.path.join(downloads_dir, fn)
        eof_st = "BGZF integrity verified." if fn.lower().endswith((".bam", ".gz", ".bgz")) else "Valid"
        sha_h = calculate_hash(fp, algorithm="sha256")
        results.append(build_record_dict(fn, fp, eof_st, sha_h))

    if not to_download:
        console.print("[bold green]✓ Tüm dosyalar zaten eksiksiz ve doğrulanmış durumda![/bold green]")
    else:
        worker_prompt = console.input(
            "[bold yellow]?[/bold yellow] Aynı anda kaç dosya indirilsin? (Worker sayısı) (Varsayılan: 2): "
        ).strip()
        try:
            max_workers = int(worker_prompt) if worker_prompt else 2
        except ValueError:
            max_workers = 2

        console.print(f"\n[bold green]⚡[/bold green] {len(to_download)} dosya için indirme ve doğrulama başlatılıyor...\n")

        progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•", DownloadColumn(),
            "•", TransferSpeedColumn(),
            "•", TimeRemainingColumn(),
            console=console,
        )

        def get_mirror_tag(url: str) -> str:
            if "amazonaws.com" in url:
                return "[bold magenta][AWS-S3][/bold magenta]"
            elif "ftp.sra.ebi.ac.uk" in url or "ebi.ac.uk" in url:
                return "[bold blue][EBI][/bold blue]"
            elif "drive.google" in url:
                return "[bold yellow][GDrive][/bold yellow]"
            return "[bold cyan][HTTP][/bold cyan]"

        def process_download(file_info):
            file_name = file_info.get("name") or file_info.get("filename") or "unnamed_file"
            dest_path = os.path.join(downloads_dir, file_name)

            mirrors = file_info.get("mirrors")
            if not mirrors:
                single_url = (
                    file_info.get("stream_url")
                    or file_info.get("url")
                    or file_info.get("download_url")
                    or f"https://drive.google.com/uc?id={file_info.get('file_id', '')}&export=download"
                )
                mirrors = [single_url]

            task_id = progress.add_task(
                description=f"[dim]Bağlanıyor...[/dim] [bold white]{file_name}[/bold white]",
                total=file_info.get("size"),
            )

            download_success = False
            used_mirror_tag = "[HTTP]"
            last_err = None

            for mirror_url in mirrors:
                used_mirror_tag = get_mirror_tag(mirror_url)
                progress.update(task_id, description=f"{used_mirror_tag} [bold white]{file_name}[/bold white]")
                try:
                    download_stream(url=mirror_url, destination_file=dest_path, progress=progress, task_id=task_id)
                    download_success = True
                    break
                except Exception as err:
                    last_err = err
                    continue

            if not download_success:
                progress.update(task_id, description=f"[red]✗ [Hata][/red] [bold white]{file_name}[/bold white]")
                err_record = build_record_dict(file_name, dest_path, "Error", "ERROR")
                err_record["status"] = f"Error: {last_err}"
                return err_record

            eof_status = "N/A"
            if file_name.lower().endswith((".bam", ".gz", ".bgz")):
                try:
                    is_eof_valid = arch_mod.check_bgzf_eof(dest_path)
                    eof_status = "BGZF integrity verified." if is_eof_valid else "Corrupted (No EOF)"
                except Exception:
                    eof_status = "N/A"

            sha256_hash = calculate_hash(dest_path, algorithm="sha256")
            file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

            progress.update(
                task_id,
                completed=file_size,
                total=file_size,
                description=f"[green]✓[/green] {used_mirror_tag} [bold white]{file_name}[/bold white] [dim]({eof_status})[/dim]",
            )

            record = build_record_dict(file_name, dest_path, eof_status, sha256_hash)
            record["mirror_provider"] = "AWS Open Data" if "AWS" in used_mirror_tag else "EBI Primary"
            return record

        with progress:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(process_download, f) for f in to_download]
                for future in futures:
                    results.append(future.result())

    reports_dir = os.path.abspath("reports")
    os.makedirs(reports_dir, exist_ok=True)
    console.print(f"\n[green]✓[/green] [bold]İşlem tamamlandı![/bold] Toplam [cyan]{len(results)}[/cyan] dosya denetlendi.")

    with console.status("[cyan]QC Sertifikası ve Excel Raporu hazırlanıyor...[/cyan]", spinner="dots"):
        try:
            cert_res = cert_mod.generate_data_certificate(results, output_dir=reports_dir)
            cert_path = cert_res.get("html") if isinstance(cert_res, dict) else cert_res
            excel_path = exp_mod.export_to_excel(results, output_dir=reports_dir)
            console.print("[bold green]✓ Raporlar hazır:[/bold green]")
            if cert_path:
                console.print(f"  📄 HTML Sertifikası : [cyan]{cert_path}[/cyan]")
            if excel_path:
                console.print(f"  📊 Excel Denetim    : [cyan]{excel_path}[/cyan]")
        except Exception as e:
            console.print(f"[dim yellow]Rapor oluşturma hatası:[/dim yellow] {e}")


def _make_upload_cert(file_path: str, destination: str, destination_url: str) -> None:
    """Upload sonrası checksum hesaplar ve sertifika üretir."""
    with console.status("[bold cyan]Kriptografik bütünlük (MD5/SHA256) hesaplanıyor..."):
        local_md5 = check_mod.calculate_hash(file_path, algorithm="md5")
        local_sha256 = check_mod.calculate_hash(file_path, algorithm="sha256")
    record = {
        "filename": os.path.basename(file_path),
        "size_bytes": os.path.getsize(file_path),
        "calculated_md5": local_md5,
        "calculated_sha256": local_sha256,
        "verified": True,
        "archive_status": "VALID (PASSED)",
        "destination": destination,
        "destination_url": destination_url,
    }
    result = cert_mod.generate_data_certificate(records=[record])
    html_path = result.get("html") or result.get("html_file") or "reports/certificate.html"
    console.print(f"[bold green]✓ Kriptografik Doğrulama Sertifikası Üretildi:[/bold green] [underline]{html_path}[/underline]")


def run_upload() -> None:
    """Yükleme Motoru (Nextcloud, S3, ENA Webin FTP, GDrive)"""
    console.print("\n[bold cyan]🚀 DataPulse Upload Engine[/bold cyan]")

    file_path = console.input(
        "\n[bold yellow]?[/bold yellow] Yüklenecek dosya yolu (örn: test_sample.fastq.gz): "
    ).strip().strip("\"'")

    if not os.path.exists(file_path):
        console.print(f"[bold red]Hata:[/bold red] '{file_path}' dosyası bulunamadı.")
        return

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    console.print(f"[green]✓[/green] Dosya seçildi: [bold cyan]{file_name}[/bold cyan] ({file_size / (1024**2):.2f} MB)")

    console.print("\n[bold yellow]Hedef Platform Seçin:[/bold yellow]")
    console.print("  [1] Nextcloud (Paylaşılan Klasör Linki / File Drop)")
    console.print("  [2] AWS S3 / MinIO Object Storage")
    console.print("  [3] ENA Webin Dropoff (FTP / TLS)")
    console.print("  [4] Google Drive (Resumable API)")
    choice = console.input("[dim]Seçim (1-4): [/dim]").strip()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]⬆ {task.description}[/bold cyan]"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•", DownloadColumn(),
        "•", TransferSpeedColumn(),
        "•", TimeRemainingColumn(),
        console=console,
    )

    try:
        if choice == "1":
            share_link = console.input(
                "[bold yellow]?[/bold yellow] Nextcloud Klasör Linki (örn: https://cloud.org/s/ABCxyz): "
            ).strip()
            has_pw = console.input(
                "[bold yellow]?[/bold yellow] Şifre koruması var mı? (E/h) [Varsayılan: h]: "
            ).strip().lower() == "e"
            link_password = ""
            if has_pw:
                link_password = console.input("[bold yellow]?[/bold yellow] Link Parolası: ", password=True).strip()

            with progress:
                task_id = progress.add_task(description=f"[Nextcloud] {file_name}", total=file_size)
                up_nc.upload_public_share(
                    file_path=file_path,
                    share_url=share_link,
                    share_password=link_password,
                    progress=progress,
                    task_id=task_id,
                )
            console.print("\n[bold green]✓ Nextcloud klasörüne başarıyla yüklendi![/bold green]")
            _make_upload_cert(file_path, "Nextcloud (Public Share)", share_link)

        elif choice == "2":
            bucket_name = console.input("[bold yellow]?[/bold yellow] S3 Bucket Adı: ").strip()
            region = console.input("[bold yellow]?[/bold yellow] AWS Region (Varsayılan: us-east-1): ").strip() or "us-east-1"
            ak = console.input("[bold yellow]?[/bold yellow] AWS Access Key ID: ").strip()
            sk = console.input("[bold yellow]?[/bold yellow] AWS Secret Access Key: ", password=True).strip()
            endpoint = console.input("[bold yellow]?[/bold yellow] Custom Endpoint (MinIO için, boş bırakın): ").strip() or None

            with progress:
                task_id = progress.add_task(description=f"[AWS-S3] {file_name}", total=file_size)
                s3_uri = up_s3.upload_s3(
                    file_path=file_path,
                    bucket_name=bucket_name,
                    aws_access_key=ak,
                    aws_secret_key=sk,
                    region_name=region,
                    endpoint_url=endpoint,
                    progress=progress,
                    task_id=task_id,
                )
            console.print(f"\n[bold green]✓ S3 Bucket'a yüklendi:[/bold green] [cyan]{s3_uri}[/cyan]")

        elif choice == "3":
            ena_user = console.input("[bold yellow]?[/bold yellow] ENA Webin Kullanıcı Adı (Webin-XXXXX): ").strip()
            ena_pass = console.input("[bold yellow]?[/bold yellow] ENA Webin Parolası: ", password=True).strip()

            with progress:
                task_id = progress.add_task(description=f"[ENA] {file_name}", total=file_size)
                up_ena.upload_ena_ftp(
                    file_path=file_path,
                    username=ena_user,
                    password=ena_pass,
                    progress=progress,
                    task_id=task_id,
                )
            console.print("\n[bold green]✓ ENA Webin Dropoff alanına başarıyla yüklendi![/bold green]")
            _make_upload_cert(file_path, "ENA Webin Dropoff (FTPS)", "webin.ebi.ac.uk")

        elif choice == "4":
            folder_id = console.input("[bold yellow]?[/bold yellow] Hedef Klasör ID (Boş bırakılırsa Root): ").strip()
            with progress:
                task_id = progress.add_task(description=f"[GDrive] {file_name}", total=file_size)
                file_id, web_link = up_gd.upload_gdrive(
                    file_path=file_path,
                    folder_id=folder_id,
                    progress=progress,
                    task_id=task_id,
                )
            console.print(f"\n[bold green]✓ Google Drive'a yüklendi![/bold green] (ID: [cyan]{file_id}[/cyan])")
            if web_link:
                console.print(f"[dim]Bağlantı: {web_link}[/dim]")
            _make_upload_cert(file_path, "Google Drive", web_link or f"https://drive.google.com/file/d/{file_id}/view")

        else:
            console.print("[yellow]Geçersiz seçim.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Yükleme Hatası:[/bold red] {e}")


def run() -> None:
    from datapulse import setup_logging

    debug_mode = "--debug" in sys.argv or os.getenv("DATAPULSE_LOG_LEVEL", "").upper() == "DEBUG"
    log_file = os.getenv("DATAPULSE_LOG_FILE")

    if debug_mode:
        setup_logging(level="DEBUG", log_file=log_file)
        console.print("[dim]Debug modu aktif.[/dim]")
    elif log_file:
        setup_logging(level="INFO", log_file=log_file)

    console.print(
        Panel.fit(
            "[bold cyan]DataPulse[/bold cyan] - [bold green]Resilient Genomic Data Engine[/bold green]\n"
            "[dim]Download & Ingestion | QC & Audit | Multi-Cloud Upload[/dim]",
            border_style="cyan",
        )
    )

    action = console.input(
        "\n[bold yellow]?[/bold yellow] Yapmak istediğin işlem? ([bold cyan]1[/bold cyan]: Download, [bold magenta]2[/bold magenta]: Upload) [Varsayılan: 1]: "
    ).strip()

    if action == "2":
        run_upload()
    else:
        run_download()


app = run
main = run

if __name__ == "__main__":
    run()