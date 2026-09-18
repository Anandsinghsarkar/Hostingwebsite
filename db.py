import sqlite3, os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'hosting.db')


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        file_limit INTEGER DEFAULT 2,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS scripts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS install_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        module TEXT,
        status TEXT,
        log TEXT,
        created_at TEXT
    )''')
    conn.commit()
    conn.close()


def create_user(username, password_hash, is_admin=0, file_limit=2):
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, is_admin, file_limit, created_at) VALUES (?,?,?,?,?)',
            (username, password_hash, is_admin, file_limit, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    return row


def get_user_by_id(uid):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    conn.close()
    return row


def list_users():
    conn = get_db()
    rows = conn.execute('SELECT * FROM users ORDER BY id').fetchall()
    conn.close()
    return rows


def update_user_limit(uid, limit):
    conn = get_db()
    conn.execute('UPDATE users SET file_limit=? WHERE id=?', (limit, uid))
    conn.commit()
    conn.close()


def delete_user(uid):
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id=?', (uid,))
    conn.execute('DELETE FROM scripts WHERE user_id=?', (uid,))
    conn.commit()
    conn.close()


def add_script(user_id, name, stype):
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO scripts (user_id, name, type, created_at) VALUES (?,?,?,?)',
        (user_id, name, stype, datetime.now().isoformat())
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def get_script(sid):
    conn = get_db()
    row = conn.execute('SELECT * FROM scripts WHERE id=?', (sid,)).fetchone()
    conn.close()
    return row


def list_scripts(user_id):
    conn = get_db()
    rows = conn.execute('SELECT * FROM scripts WHERE user_id=? ORDER BY id DESC', (user_id,)).fetchall()
    conn.close()
    return rows


def count_scripts(user_id):
    conn = get_db()
    n = conn.execute('SELECT COUNT(*) FROM scripts WHERE user_id=?', (user_id,)).fetchone()[0]
    conn.close()
    return n


def delete_script(sid):
    conn = get_db()
    conn.execute('DELETE FROM scripts WHERE id=?', (sid,))
    conn.commit()
    conn.close()


def log_install(user_id, module, status, log):
    conn = get_db()
    conn.execute(
        'INSERT INTO install_logs (user_id, module, status, log, created_at) VALUES (?,?,?,?,?)',
        (user_id, module, status, log[:2000], datetime.now().isoformat())
    )
    conn.commit()
    conn.close()