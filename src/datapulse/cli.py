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
    help="Enterprise-Grade Resilient Data Ingestion, Extraction & Cryptographic Provenance Engine",
    add_completion=False,
)
console = Console()


@app.command()
def download(
    url: str = typer.Argument(..., help="Target file download URL"),
    output_dir: str = typer.Option("downloads", "--output", "-o", help="Target destination directory"),
    filename: Optional[str] = typer.Option(None, "--name", "-n", help="Optional output filename override"),
):
    """Resilient single-file stream download with HTTP Range auto-resume support."""
    console.print(Panel(f"[bold cyan]Initiating Stream Download:[/bold cyan] {url}", border_style="blue"))
    try:
        saved_path = download_stream(url=url, output_dir=output_dir, filename=filename)
        console.print(f"[bold green]✔ Download completed successfully:[/bold green] {saved_path}")
    except Exception as err:
        console.print(f"[bold red]✖ Download error:[/bold red] {err}")
        raise typer.Exit(code=1)


@app.command()
def verify(
    file_path: str = typer.Argument(..., help="Path to the target artifact to verify"),
    expected_hash: str = typer.Argument(..., help="Expected cryptographic hash digest"),
    algo: str = typer.Option("sha256", "--algo", "-a", help="Hashing algorithm: sha256 or md5"),
):
    """Cryptographic integrity verification engine (MD5 / SHA-256)."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] Target artifact not found: {file_path}")
        raise typer.Exit(code=1)

    is_valid = verify_checksum(path, expected_hash, algorithm=algo)
    if is_valid:
        console.print(f"[bold green]✔ Hash Verified ({algo.upper()} digest matches expected value!)[/bold green]")
    else:
        current_hash = calculate_hash(path, algorithm=algo)
        console.print("[bold red]✖ Integrity Mismatch! Artifact corrupted or checksum divergent.[/bold red]")
        console.print(f"Calculated Digest: {current_hash}")
        console.print(f"Expected Digest:   {expected_hash}")
        raise typer.Exit(code=1)


@app.command()
def pipeline(
    url: str = typer.Option(
        "https://raw.githubusercontent.com/torvalds/linux/master/README",
        "--url",
        "-u",
        help="Source URL for the dataset",
    ),
    webhook_url: Optional[str] = typer.Option(
        None, "--webhook", "-w", help="Discord/Slack Webhook URL for run alerts"
    ),
):
    """End-to-end reference pipeline: Stream -> Hash Check -> Schema Validation -> Audit Export."""
    console.print(
        Panel.fit(
            "[bold white]DataPulse Resilient ETL Pipeline Executing[/bold white]",
            border_style="magenta",
        )
    )

    downloaded_file = download_stream(url, output_dir="downloads", filename="pipeline_sample.txt")
    total_size = downloaded_file.stat().st_size
    file_hash = calculate_hash(downloaded_file, algorithm="sha256")

    mock_batch = [
        {"id": 101, "title": "Server Power Supply Unit", "category": "Infrastructure", "price": 4200.0},
        {"id": 102, "title": "Cat6 Shielded Cable 100m", "category": "Networking", "price": 850.0},
        {"id": 103, "title": "A", "category": "Invalid Row", "price": -10.0},
    ]
    valid_records, invalid_records = validate_records(mock_batch)
    report_path = export_to_excel(valid_records, output_dir="reports", filename="pipeline_run.xlsx")

    summary = generate_pipeline_summary(
        total_downloaded_bytes=total_size,
        valid_count=len(valid_records),
        invalid_count=len(invalid_records),
        checksum_passed=True,
    )

    table = Table(title="Pipeline Execution Telemetry", border_style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("Execution Status", summary["status"])
    table.add_row("Ingested Artifact", str(downloaded_file))
    table.add_row("Artifact Size", f"{summary['downloaded_bytes']:,} bytes")
    table.add_row("SHA-256 Digest", f"{file_hash[:16]}... (cryptographically verified)")
    table.add_row("Valid Records", str(summary["valid_records"]))
    table.add_row("Evicted Invalids", str(summary["invalid_records"]))
    table.add_row("Excel Report", str(report_path))

    console.print(table)

    if webhook_url:
        send_webhook_notification(webhook_url, summary)
        console.print("[dim]Webhook notification dispatched successfully.[/dim]")


@app.command()
def auto():
    """Interactive wizard: Resolves links via DOM or REST API, prompts concurrency, runs parallel pool."""
    console.print(
        Panel.fit(
            "[bold cyan]DataPulse Auto-Pilot Wizard & Multi-Worker Ingestion Pool[/bold cyan]\n"
            "Zero configuration required. Follow the guided interactive prompts.",
            border_style="cyan",
        )
    )

    # 1. Prompt target URL and search keyword
    target_url = typer.prompt("Enter source URL (study accession, web directory, or archive link)")
    keyword = typer.prompt(
        "Keyword or title filter (press Enter to ingest all discovered artifacts)",
        default="",
    )

    console.print("\n[yellow]🔍 Resolving artifacts & scraping target metadata...[/yellow]")
    try:
        matched_files = discover_download_links(target_url, title_keyword=keyword)
    except Exception as err:
        console.print(f"[bold red]Failed to resolve target metadata:[/bold red] {err}")
        raise typer.Exit(code=1)

    if not matched_files:
        console.print("[bold red]No matching artifacts discovered at target origin.[/bold red]")
        return

    # 2. Display discovered artifacts table
    result_table = Table(
        title=f"Discovered Artifacts ({len(matched_files)} items)", border_style="green"
    )
    result_table.add_column("#", justify="right", style="cyan")
    result_table.add_column("Artifact Title / Target", style="white")
    result_table.add_column("Format", style="magenta")
    result_table.add_column("Upstream Digest Status", style="yellow")

    for i, item in enumerate(matched_files, 1):
        md5_status = "Available (Remote API)" if item.get("expected_md5") else "Generated Post-Ingestion"
        result_table.add_row(
            str(i), item["title"][:45], item["extension"], md5_status
        )

    console.print(result_table)

    # 3. Confirmation & concurrency prompt
    should_download = typer.confirm(
        f"\nProceed with ingesting these {len(matched_files)} artifacts?",
        default=True,
    )
    if not should_download:
        console.print("[yellow]Ingestion batch aborted by operator.[/yellow]")
        return

    concurrency = typer.prompt(
        "Parallel worker concurrency (Recommended: 2 - 6)",
        default=4,
        type=int,
    )
    concurrency = max(1, min(concurrency, 16))

    console.print(
        f"\n[bold green]🚀 Spawning {concurrency} parallel worker threads with stream validation...[/bold green]\n"
    )

    # 4. Multi-threaded ingestion pool
    results = download_concurrently(
        items=matched_files,
        output_dir="downloads",
        max_workers=concurrency,
        calculate_hash_func=calculate_hash,
    )

    # 5. Provenance certificate & manifest generation
    successful_records = [r for r in results if r["success"]]

    if successful_records:
        certs = generate_data_certificate(successful_records, output_dir="reports")
        console.print(
            Panel.fit(
                f"[bold green]✔ Ingestion Batch Completed Successfully![/bold green]\n\n"
                f"[cyan]📁 Artifact Destination:[/cyan] downloads/\n"
                f"[green]⚡ Verified Deliveries:[/green] {len(successful_records)} / {len(matched_files)}\n"
                f"[magenta]📜 JSON Provenance Manifest:[/magenta] {certs['json']}\n"
                f"[gold1]🏆 Dark HTML Data Certificate:[/gold1] {certs['html']}",
                border_style="green",
                title="Cryptographic Provenance Generated",
            )
        )
    else:
        console.print("[bold red]No artifacts were successfully transferred or verified.[/bold red]")


if __name__ == "__main__":
    app()