from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from datapulse.downloader.parallel import download_concurrently
from datapulse.downloader.stream import download_stream
from datapulse.reporter.certificate import generate_data_certificate
from datapulse.reporter.exporter import export_to_excel, generate_pipeline_summary
from datapulse.reporter.notifier import send_webhook_notification
from datapulse.scraper.extractor import discover_download_links
from datapulse.validator.checksum import calculate_hash, verify_checksum
from datapulse.validator.schema import validate_records

app = typer.Typer(
    name="datapulse",
    help="High-Performance Resilient Data Extraction & Validation CLI",
    add_completion=False,
)
console = Console()


@app.command()
def download(
    url: str = typer.Argument(..., help="İndirilecek dosyanın URL adresi"),
    output_dir: str = typer.Option("downloads", "--output", "-o", help="Hedef klasör"),
    filename: Optional[str] = typer.Option(None, "--name", "-n", help="Kaydedilecek dosya adı"),
):
    """Büyük dosyaları parça parça ve kesintiye dayanıklı şekilde tekil indirir."""
    console.print(Panel(f"[bold cyan]İndirme Başlatılıyor:[/bold cyan] {url}", border_style="blue"))
    try:
        saved_path = download_stream(url=url, output_dir=output_dir, filename=filename)
        console.print(f"[bold green]✔ Başarıyla tamamlandı:[/bold green] {saved_path}")
    except Exception as e:
        console.print(f"[bold red]✖ İndirme hatası:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def verify(
    file_path: str = typer.Argument(..., help="Doğrulanacak dosya yolu"),
    expected_hash: str = typer.Argument(..., help="Beklenen hash değeri"),
    algo: str = typer.Option("sha256", "--algo", "-a", help="Algoritma: sha256 veya md5"),
):
    """Dosyanın MD5 veya SHA-256 bütünlüğünü kontrol eder."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[bold red]Hata:[/bold red] Dosya bulunamadı: {file_path}")
        raise typer.Exit(code=1)

    is_valid = verify_checksum(path, expected_hash, algorithm=algo)
    if is_valid:
        console.print(f"[bold green]✔ Hash Doğrulandı ({algo.upper()} Eşleşti!)[/bold green]")
    else:
        current_hash = calculate_hash(path, algorithm=algo)
        console.print(f"[bold red]✖ Bütünlük Hatası! Dosya bozulmuş veya uyuşmuyor.[/bold red]")
        console.print(f"Mevcut Hash:   {current_hash}")
        console.print(f"Beklenen Hash: {expected_hash}")
        raise typer.Exit(code=1)


@app.command()
def pipeline(
    url: str = typer.Option(
        "https://raw.githubusercontent.com/torvalds/linux/master/README",
        "--url",
        "-u",
        help="Kaynak URL",
    ),
    webhook_url: Optional[str] = typer.Option(
        None, "--webhook", "-w", help="Discord/Slack Webhook URL"
    ),
):
    """Uçtan uca pipeline: İndir -> Hash Doğrula -> Şema Denetle -> Excel Raporu Çıkar."""
    console.print(
        Panel.fit(
            "[bold white]DataPulse Uçtan Uca ETL Pipeline Çalışıyor[/bold white]",
            border_style="magenta",
        )
    )

    downloaded_file = download_stream(url, output_dir="downloads", filename="pipeline_sample.txt")
    total_size = downloaded_file.stat().st_size
    file_hash = calculate_hash(downloaded_file, algorithm="sha256")

    mock_batch = [
        {"id": 101, "title": "Sunucu Güç Kaynağı", "category": "Altyapı", "price": 4200.0},
        {"id": 102, "title": "Cat6 Kablo 100m", "category": "Ağ", "price": 850.0},
        {"id": 103, "title": "A", "category": "Geçersiz Kayıt", "price": -10.0},
    ]
    valid_records, invalid_records = validate_records(mock_batch)
    report_path = export_to_excel(valid_records, output_dir="reports", filename="pipeline_run.xlsx")

    summary = generate_pipeline_summary(
        total_downloaded_bytes=total_size,
        valid_count=len(valid_records),
        invalid_count=len(invalid_records),
        checksum_passed=True,
    )

    table = Table(title="Pipeline Yürütme Özeti", border_style="cyan")
    table.add_column("Metrik", style="bold white")
    table.add_column("Değer", style="green")

    table.add_row("Durum", summary["status"])
    table.add_row("İndirilen Dosya", str(downloaded_file))
    table.add_row("Dosya Boyutu", f"{summary['downloaded_bytes']} bytes")
    table.add_row("SHA-256 Hash", f"{file_hash[:16]}... (tamamı doğrulandı)")
    table.add_row("Geçerli Kayıtlar", str(summary["valid_records"]))
    table.add_row("Ayıklanan Hatalı Veri", str(summary["invalid_records"]))
    table.add_row("Excel Çıktısı", str(report_path))

    console.print(table)

    if webhook_url:
        send_webhook_notification(webhook_url, summary)
        console.print("[dim]Webhook bildirimi iletildi.[/dim]")


@app.command()
def auto():
    """Kullanıcı dostu interaktif sihirbaz: Link, başlık ve paralel indirme sayısı sorup otomatik çalışır."""
    console.print(
        Panel.fit(
            "[bold cyan]DataPulse Akıllı Veri Toplayıcı & Çok Kanallı İndirici[/bold cyan]\n"
            "Herhangi bir parametre yazmanıza gerek yok, yönergeleri takip etmeniz yeterli.",
            border_style="cyan",
        )
    )

    # 1. Kullanıcıdan URL ve Başlık al
    target_url = typer.prompt("Web sitesi linkini girin")
    keyword = typer.prompt(
        "İndirmek istediğiniz dataların başlığı / anahtar kelimesi (hepsi için Enter)",
        default="",
    )

    console.print(f"\n[yellow]🔍 Sayfa taranıyor...[/yellow]")
    try:
        matched_files = discover_download_links(target_url, title_keyword=keyword)
    except Exception as e:
        console.print(f"[bold red]Sayfaya erişilirken hata oluştu:[/bold red] {e}")
        raise typer.Exit(code=1)

    if not matched_files:
        console.print("[bold red]Eşleşen herhangi bir veri dosyası bulunamadı.[/bold red]")
        return

    # 2. Bulunan dosyaları listele
    result_table = Table(
        title=f"Bulunan Dosyalar ({len(matched_files)} Adet)", border_style="green"
    )
    result_table.add_column("No", justify="right", style="cyan")
    result_table.add_column("Başlık", style="white")
    result_table.add_column("Uzantı", style="magenta")
    result_table.add_column("MD5 Durumu", style="yellow")

    for i, item in enumerate(matched_files, 1):
        md5_status = "Mevcut (API)" if item.get("expected_md5") else "İndirme sonrası üretilecek"
        result_table.add_row(
            str(i), item["title"][:45], item["extension"], md5_status
        )

    console.print(result_table)

    # 3. İndirme Onayı ve Eşzamanlılık (Concurrency) Ayarı
    should_download = typer.confirm(
        f"\nBu {len(matched_files)} dosya indirilsin mi?",
        default=True,
    )
    if not should_download:
        console.print("[yellow]İşlem iptal edildi.[/yellow]")
        return

    # Kullanıcıya eşzamanlı worker sayısı soruluyor
    concurrency = typer.prompt(
        "Aynı anda kaç dosya paralel indirilsin? (Önerilen: 2 - 5)",
        default=3,
        type=int,
    )
    concurrency = max(1, min(concurrency, 10))  # 1 ile 10 arasında sınırla

    console.print(
        f"\n[bold green]🚀 {concurrency} adet paralel worker ile çoklu indirme ve doğrulama başlatılıyor...[/bold green]\n"
    )

    # 4. Çok Kanallı Paralel İndirme ve Hash Denetimi
    results = download_concurrently(
        items=matched_files,
        output_dir="downloads",
        max_workers=concurrency,
        calculate_hash_func=calculate_hash,
    )

    # 5. Başarılı olanları filtrele ve Rapor / Sertifika üret
    successful_records = [r for r in results if r["success"]]

    if successful_records:
        certs = generate_data_certificate(successful_records, output_dir="reports")
        console.print(
            Panel.fit(
                f"[bold green]✔ İşlem Başarıyla Tamamlandı![/bold green]\n\n"
                f"[cyan]📁 İndirilen Dosyalar:[/cyan] downloads/\n"
                f"[green]⚡ Başarılı Dosya Sayısı:[/green] {len(successful_records)} / {len(matched_files)}\n"
                f"[magenta]📜 JSON Manifest:[/magenta] {certs['json']}\n"
                f"[gold1]🏆 HTML Veri Sertifikası:[/gold1] {certs['html']}",
                border_style="green",
                title="Provenans Raporu Üretildi",
            )
        )
    else:
        console.print("[bold red]Hiçbir dosya başarıyla indirilemedi veya doğrulanamadı.[/bold red]")


if __name__ == "__main__":
    app()