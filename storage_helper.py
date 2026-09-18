# -*- coding: utf-8 -*-
"""
Firebase Storage helper — scripts ko Render restart ke baad bachane ke liye.
"""
import os
from firebase_config import get_bucket


def upload_script_file(local_path, user_id, script_id, filename):
    try:
        bucket = get_bucket()
        if not bucket:
            return None
        blob_path = f"scripts/{user_id}/{script_id}/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        print(f"✅ Uploaded: {blob_path}")
        return blob_path
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return None


def upload_script_folder(local_dir, user_id, script_id):
    try:
        bucket = get_bucket()
        if not bucket:
            return {}
        uploaded = {}
        for root, dirs, files in os.walk(local_dir):
            for fn in files:
                local_file = os.path.join(root, fn)
                rel = os.path.relpath(local_file, local_dir).replace('\\', '/')
                blob_path = f"scripts/{user_id}/{script_id}/{rel}"
                bucket.blob(blob_path).upload_from_filename(local_file)
                uploaded[rel] = blob_path
        print(f"✅ Uploaded {len(uploaded)} files for {script_id}")
        return uploaded
    except Exception as e:
        print(f"❌ Folder upload failed: {e}")
        return {}


def download_script_folder(user_id, script_id, dest_dir):
    try:
        bucket = get_bucket()
        if not bucket:
            return False
        prefix = f"scripts/{user_id}/{script_id}/"
        blobs = list(bucket.list_blobs(prefix=prefix))
        if not blobs:
            return False
        os.makedirs(dest_dir, exist_ok=True)
        count = 0
        for blob in blobs:
            rel = blob.name[len(prefix):]
            if not rel:
                continue
            local_path = os.path.join(dest_dir, rel)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            count += 1
        print(f"✅ Downloaded {count} files for {script_id}")
        return count > 0
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


def delete_script_folder(user_id, script_id):
    try:
        bucket = get_bucket()
        if not bucket:
            return False
        prefix = f"scripts/{user_id}/{script_id}/"
        for blob in bucket.list_blobs(prefix=prefix):
            try:
                blob.delete()
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"❌ Storage delete failed: {e}")
        return False


def upload_qr_image(local_path, filename):
    """Admin QR code upload kare to Firebase Storage me save."""
    try:
        bucket = get_bucket()
        if not bucket:
            return None
        blob_path = f"assets/qr/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"❌ QR upload failed: {e}")
        return None
