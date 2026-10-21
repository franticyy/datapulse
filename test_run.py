import os
from src.nextcloud_client import NextcloudSync
from src.datapulse.validator.checksum import calculate_hash, verify_checksum

NEXTCLOUD_URL = "https://ivo.lv.tab.digital"
USERNAME = "gulberkayy14@gmail.com"
APP_PASSWORD = "PSsJk-Pe57n-DDEdB-ZZzRJ-KsrA2"

client = NextcloudSync(
    base_url=NEXTCLOUD_URL,
    username=USERNAME,
    app_password=APP_PASSWORD,
    chunk_size_mb=5
)

dummy_file = "test_large_run.fastq"
if not os.path.exists(dummy_file):
    with open(dummy_file, "wb") as f:
        f.seek(12 * 1024 * 1024 - 1)
        f.write(b"\0")

print("Test yüklemesi başlıyor...")
client.upload_file_chunked(dummy_file, remote_folder="DataPulse_Bench")

# Mevcut validator modülüyle doğrulama
local_md5 = calculate_hash(dummy_file, algorithm="md5")
print(f"\nYerel MD5 : {local_md5}")

remote_path = f"DataPulse_Bench/{dummy_file}"
remote_hash = client.get_remote_checksum(remote_path)
print(f"Nextcloud Hash : {remote_hash if remote_hash else 'Sunucu anlık header dönmedi'}")

if remote_hash:
    is_valid = verify_checksum(dummy_file, remote_hash.split(":")[-1], algorithm="md5")
    print(f"Bütünlük Durumu: {'BAŞARILI' if is_valid else 'BOZUK VERİ'}")