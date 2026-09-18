# -*- coding: utf-8 -*-
"""
Firebase Admin SDK initialization.
Service account JSON file name env me set karo: FIREBASE_KEY_PATH
"""
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
KEY_PATH = os.environ.get('FIREBASE_KEY_PATH', os.path.join(BASE_DIR, 'firebase-key.json'))

_db = None
_bucket = None
_initialized = False


def init_firebase():
    global _db, _bucket, _initialized
    if _initialized:
        return _db, _bucket

    if not os.path.exists(KEY_PATH):
        # Try env var with JSON content
        key_json = os.environ.get('FIREBASE_KEY_JSON')
        if key_json:
            cred_dict = json.loads(key_json)
            cred = credentials.Certificate(cred_dict)
        else:
            raise RuntimeError(
                f"Firebase key not found at {KEY_PATH}. "
                "Set FIREBASE_KEY_PATH or FIREBASE_KEY_JSON env var."
            )
    else:
        cred = credentials.Certificate(KEY_PATH)

    firebase_admin.initialize_app(cred, {
        'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', '')
    })

    _db = firestore.client()
    try:
        _bucket = storage.bucket()
    except Exception:
        _bucket = None

    _initialized = True
    print("✅ Firebase initialized")
    return _db, _bucket


def get_db():
    if not _initialized:
        init_firebase()
    return _db


def get_bucket():
    if not _initialized:
        init_firebase()
    return _bucket