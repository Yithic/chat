import datetime

from django.conf import settings
from google.cloud import storage
from django.utils.text import get_valid_filename


def get_gcs_bucket():
    storage_client = storage.Client()
    bucket_name = getattr(settings, 'GCS_BUCKET_NAME', 'your-default-bucket-name')
    return storage_client.bucket(bucket_name)


def generate_upload_url(user_id, file_name, content_type):
    bucket = get_gcs_bucket()
    safe_file_name = get_valid_filename(file_name)
    if not safe_file_name:
        safe_file_name = "unnamed_file"
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    gcs_file_id = f"uploads/user_{user_id}/{timestamp}_{safe_file_name}"
    blob = bucket.blob(gcs_file_id)
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="PUT",
        content_type=content_type,
    )
    return signed_url, gcs_file_id


def generate_download_url(gcs_file_id):
    bucket = get_gcs_bucket()
    blob = bucket.blob(gcs_file_id)
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=60),
        method="GET",
    )


def user_owns_media_path(user_id, media_gcs_id):
    prefix = f"uploads/user_{user_id}/"
    return media_gcs_id.startswith(prefix)

def delete_gcs_blob(gcs_file_id):
    """Deletes a file from GCS bucket given its path/ID."""
    if not gcs_file_id:
        return
    try:
        bucket = get_gcs_bucket()
        blob = bucket.blob(gcs_file_id)
        # Directly delete the blob; it throws an exception if it doesn't exist
        blob.delete()
    except Exception as e:
        # Log it but don't crash the app if a file was already missing
        print(f"GCS Blob Deletion Error for {gcs_file_id}: {e}")
