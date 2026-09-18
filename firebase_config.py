# -*- coding: utf-8 -*-
"""
Firebase Admin SDK initialization.
Koi bhi cheez is file me import NAHI karo — ye base file hai.
"""
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
KEY_PATH = os.environ.get('FIREBASE_KEY_PATH',
                          os.path.join(BASE_DIR, 'firebase-key.json'))

_db = None
_bucket = None
_initialized = False


def init_firebase():
    """Initialize Firebase once. Safe to call multiple times."""
    global _db, _bucket, _initialized

    if _initialized:
        return _db, _bucket

    # --- Load credentials ---
    key_json = os.environ.get('FIREBASE_KEY_JSON')

    if key_json:
        try:
            cred_dict = json.loads(key_json)
            cred = credentials.Certificate(cred_dict)
        except Exception as e:
            raise RuntimeError(f"Invalid FIREBASE_KEY_JSON: {e}")
    elif os.path.exists(KEY_PATH):
        cred = credentials.Certificate(KEY_PATH)
    else:
        raise RuntimeError(
            "Firebase key not found. Set FIREBASE_KEY_JSON env var "
            "or place firebase-key.json in project root."
        )

    bucket_name = os.environ.get('FIREBASE_STORAGE_BUCKET', '')

    # Avoid double-init
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            'storageBucket': bucket_name
        })

    _db = firestore.client()

    try:
        _bucket = storage.bucket()
    except Exception as e:
        print(f"⚠️ Storage bucket not available: {e}")
        _bucket = None

    _initialized = True
    print("✅ Firebase initialized")
    return _db, _bucket


def get_db():
    """Get Firestore client. Auto-init if needed."""
    if not _initialized:
        init_firebase()
    return _db


def get_bucket():
    """Get Firebase Storage bucket."""
    if not _initialized:
        init_firebase()
    return _bucket
