# -*- coding: utf-8 -*-
"""
Firestore database helpers.
Collections: users, scripts, payments, settings, install_logs
"""
import os
from datetime import datetime
from firebase_config import get_db


# --- Admin email whitelist (Render env var se) ---
# Example: ADMIN_EMAILS=adminanandkumar@gmail.com,other@gmail.com
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get('ADMIN_EMAILS', '').split(',')
    if e.strip()
]


def _now():
    return datetime.utcnow().isoformat()


# ==================== USERS ====================

def get_user(uid):
    db = get_db()
    doc = db.collection('users').document(uid).get()
    return doc.to_dict() if doc.exists else None


def create_or_update_user(uid, email, name, picture=''):
    """Login pe call hota hai. Whitelist email = auto admin."""
    db = get_db()
    ref = db.collection('users').document(uid)
    existing = ref.get()

    is_admin_email = email.lower() in ADMIN_EMAILS

    data = {
        'email': email,
        'name': name,
        'picture': picture,
        'last_login': _now(),
    }

    if not existing.exists:
        data.update({
            'is_admin': is_admin_email,
            'file_limit': 999 if is_admin_email else 2,
            'plan': 'premium' if is_admin_email else 'free',
            'created_at': _now(),
        })
        ref.set(data)
    else:
        # Agar email whitelist me hai aur already admin nahi hai, to promote karo
        old_data = existing.to_dict()
        if is_admin_email and not old_data.get('is_admin'):
            data['is_admin'] = True
            if old_data.get('file_limit', 2) < 999:
                data['file_limit'] = 999
        ref.update(data)

    return ref.get().to_dict()


def list_users(limit=500):
    db = get_db()
    users = []
    for doc in db.collection('users').limit(limit).stream():
        d = doc.to_dict()
        d['uid'] = doc.id
        users.append(d)
    users.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return users


def update_user(uid, data):
    db = get_db()
    db.collection('users').document(uid).update(data)


def set_user_limit(uid, limit):
    update_user(uid, {'file_limit': int(limit)})


def set_user_plan(uid, plan):
    update_user(uid, {'plan': plan})


def make_admin(uid, is_admin=True):
    update_user(uid, {'is_admin': bool(is_admin)})


def delete_user(uid):
    db = get_db()
    for doc in db.collection('scripts').where('user_id', '==', uid).stream():
        doc.reference.delete()
    db.collection('users').document(uid).delete()


def count_users():
    db = get_db()
    return len(list(db.collection('users').stream()))


# ==================== SCRIPTS ====================

def add_script(sid, user_id, name, stype, storage_path=''):
    db = get_db()
    db.collection('scripts').document(sid).set({
        'user_id': user_id,
        'name': name,
        'type': stype,
        'running': False,
        'storage_path': storage_path,
        'created_at': _now(),
    })
    return sid


def get_script(sid):
    db = get_db()
    doc = db.collection('scripts').document(sid).get()
    if doc.exists:
        d = doc.to_dict()
        d['id'] = doc.id
        return d
    return None


def list_scripts(user_id=None):
    db = get_db()
    q = db.collection('scripts')
    if user_id:
        q = q.where('user_id', '==', user_id)
    items = []
    for doc in q.stream():
        d = doc.to_dict()
        d['id'] = doc.id
        items.append(d)
    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return items


def update_script(sid, data):
    db = get_db()
    db.collection('scripts').document(sid).update(data)


def delete_script(sid):
    db = get_db()
    db.collection('scripts').document(sid).delete()


def count_scripts(user_id):
    return len(list_scripts(user_id))


# ==================== PAYMENTS ====================

def add_payment(user_id, amount, method, status, note=''):
    db = get_db()
    pid = db.collection('payments').document().id
    db.collection('payments').document(pid).set({
        'user_id': user_id,
        'amount': float(amount),
        'method': method,
        'status': status,
        'note': note,
        'created_at': _now(),
    })
    return pid


def list_payments(user_id=None, limit=200):
    db = get_db()
    q = db.collection('payments')
    if user_id:
        q = q.where('user_id', '==', user_id)
    items = []
    for doc in q.limit(limit).stream():
        d = doc.to_dict()
        d['id'] = doc.id
        items.append(d)
    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return items


# ==================== SETTINGS ====================

def get_settings():
    db = get_db()
    doc = db.collection('settings').document('global').get()
    if doc.exists:
        return doc.to_dict()
    return {
        'pricing': {'free': 0, 'premium': 199, 'business': 499},
        'offer': 'Get 50% OFF on Premium Plan',
    }


def update_settings(data):
    db = get_db()
    db.collection('settings').document('global').set(data, merge=True)


# ==================== INSTALL LOGS ====================

def log_install(user_id, module, status, log):
    """Installation log save karo (auto-install ka record)."""
    try:
        db = get_db()
        pid = db.collection('install_logs').document().id
        db.collection('install_logs').document(pid).set({
            'user_id': user_id,
            'module': module,
            'status': status,
            'log': (log or '')[:2000],
            'created_at': _now(),
        })
    except Exception as e:
        print(f"⚠️ log_install failed: {e}")
