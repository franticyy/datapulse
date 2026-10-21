import os
import boto3
from boto3.s3.transfer import TransferConfig


class ProgressPercentage:
    def __init__(self, progress=None, task_id=None):
        self._progress = progress
        self._task_id = task_id

    def __call__(self, bytes_amount):
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, advance=bytes_amount)


def upload_s3(file_path: str, bucket_name: str, object_key: str = None, aws_access_key: str = None, aws_secret_key: str = None, region_name: str = "us-east-1", endpoint_url: str = None, progress=None, task_id=None):
    """
    AWS S3 veya yerel MinIO/Ceph sunucusuna multipart stream ile yükleme yapar.
    """
    file_name = os.path.basename(file_path)
    if not object_key:
        object_key = file_name

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=region_name,
        endpoint_url=endpoint_url,
    )

    # 15 MB üzeri dosyaları otomatik multipart olarak paralel aktarır
    config = TransferConfig(
        multipart_threshold=15 * 1024 * 1024,
        max_concurrency=10,
        multipart_chunksize=10 * 1024 * 1024,
        use_threads=True,
    )

    s3_client.upload_file(
        Filename=file_path,
        Bucket=bucket_name,
        Key=object_key,
        Config=config,
        Callback=ProgressPercentage(progress, task_id),
    )

    return f"s3://{bucket_name}/{object_key}"