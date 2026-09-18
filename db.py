# -*- coding: utf-8 -*-
"""
Firestore database helpers.
"""
import os
from datetime import datetime
from firebase_config import get_db


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
            'plan_expiry': None,
            'created_at': _now(),
        })
        ref.set(data)
    else:
        old = existing.to_dict()
        if is_admin_email and not old.get('is_admin'):
            data['is_admin'] = True
            if old.get('file_limit', 2) < 999:
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


def set_user_plan(uid, plan, days=30):
    """Plan set + expiry set."""
    from datetime import timedelta
    expiry = (datetime.utcnow() + timedelta(days=days)).isoformat()
    update_user(uid, {'plan': plan, 'plan_expiry': expiry})


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

def add_payment(user_id, amount, method, status, note='', screenshot_url=''):
    db = get_db()
    pid = db.collection('payments').document().id
    db.collection('payments').document(pid).set({
        'user_id': user_id,
        'amount': float(amount),
        'method': method,
        'status': status,
        'note': note,
        'screenshot_url': screenshot_url,
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


def update_payment_status(pid, status):
    db = get_db()
    db.collection('payments').document(pid).update({'status': status})


# ==================== SETTINGS (PRICING + QR) ====================

DEFAULT_SETTINGS = {
    'pricing': {
        'free': {'price': 0, 'bots': 2, 'days': 0},
        'premium': {'price': 199, 'bots': 20, 'days': 30},
        'business': {'price': 499, 'bots': 999, 'days': 30},
    },
    'per_bot_price': 49,      # ek extra bot ka price
    'upi_id': 'a7hosting@upi',
    'upi_name': 'A7 Hosting',
    'qr_code_url': '',        # admin upload karega
    'offer_text': 'Get 50% OFF on Premium Plan',
    'support_contact': '@a7hosting',
    'payment_note': 'Payment ke baad screenshot admin ko bhejo.',
}


def get_settings():
    db = get_db()
    doc = db.collection('settings').document('global').get()
    if doc.exists:
        data = doc.to_dict()
        # merge defaults
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    return dict(DEFAULT_SETTINGS)


def update_settings(data):
    db = get_db()
    db.collection('settings').document('global').set(data, merge=True)


# ==================== INSTALL LOGS ====================

def log_install(user_id, module, status, log):
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
