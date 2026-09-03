from pathlib import Path
from typing import Optional
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


def download_stream(
    url: str,
    output_dir: Path | str = "downloads",
    filename: Optional[str] = None,
    chunk_size: int = 1024 * 64,  # 64 KB chunklar
) -> Path:
    """
    Büyük dosyaları hafızayı tüketmeden parça parça indirir.
    Dosya yarım kalmışsa otomatik tespit edip kaldığı byte'tan devam eder.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Dosya adını belirle (verilmediyse URL'den çıkar)
    if not filename:
        filename = url.split("?")[0].rstrip("/").split("/")[-1]
        if not filename:
            filename = "downloaded_file.bin"

    target_file = output_path / filename
    existing_bytes = target_file.stat().st_size if target_file.exists() else 0

    # Kaldığı yerden devam etmek için Range header hazırla
    headers = {}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    client = httpx.Client(timeout=30.0, follow_redirects=True)

    with client.stream("GET", url, headers=headers) as response:
        # 416: Requested Range Not Satisfiable (Dosya zaten tamamen inmiş demektir)
        if response.status_code == 416:
            return target_file

        response.raise_for_status()

        # Sunucunun Range desteği verip vermediğini kontrol et (206 Partial Content)
        is_resume = response.status_code == 206
        mode = "ab" if is_resume else "wb"

        total_bytes = None
        content_length = response.headers.get("Content-Length")
        if content_length:
            total_bytes = int(content_length) + (existing_bytes if is_resume else 0)

        # Rich terminal ilerleme çubuğu
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        )

        with progress:
            task = progress.add_task(
                f"İndiriliyor: [cyan]{filename}[/cyan]",
                total=total_bytes,
                completed=existing_bytes if is_resume else 0,
            )

            with open(target_file, mode) as file:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    file.write(chunk)
                    progress.update(task, advance=len(chunk))

    return target_file