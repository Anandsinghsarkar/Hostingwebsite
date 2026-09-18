# -*- coding: utf-8 -*-
import os
import sys
import re
import zipfile
import tempfile
import shutil
import threading
import subprocess
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, abort, send_file)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import db
import runner

# --- Config ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXT = {'.py', '.js', '.zip'}

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ⚠️ IMPORTANT: Ye line Gunicorn dhundta hai
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me-in-production')
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Init database
db.init_db()


# --- Auth Helpers ---
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return db.get_user_by_id(uid)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user['is_admin']:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# --- Security Scan ---
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'\bos\.system\s*\(',
    r'\bos\.popen\s*\(',
    r'subprocess\.(Popen|call|run)\s*\([^)]*shell\s*=\s*True',
    r'\bctypes\b',
    r'__import__\s*\(\s*[\'"]os[\'"]\s*\)',
    r'shutil\.rmtree\s*\(\s*[\'"]/',
    r':\(\)\s*\{',
]


def scan_code(text):
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text):
            return False, pattern
    return True, None


# --- Routes ---
@app.route('/')
def index():
    if current_user():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or len(username) < 3:
            flash("Username must be at least 3 characters", "error")
            return render_template('register.html')
        if len(password) < 4:
            flash("Password must be at least 4 characters", "error")
            return render_template('register.html')

        ok = db.create_user(username, generate_password_hash(password))
        if not ok:
            flash("Username already exists", "error")
            return render_template('register.html')

        flash("Account created! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = db.get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))

        flash("Invalid credentials", "error")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    scripts = db.list_scripts(user['id'])

    scripts_info = []
    for s in scripts:
        status = runner.get_status(s['id'])
        scripts_info.append({'script': s, 'status': status})

    return render_template('dashboard.html', user=user,
                           scripts=scripts_info, count=len(scripts))


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    user = current_user()
    f = request.files.get('file')

    if not f or not f.filename:
        flash("No file selected", "error")
        return redirect(url_for('dashboard'))

    if db.count_scripts(user['id']) >= user['file_limit']:
        flash(f"File limit ({user['file_limit']}) reached", "error")
        return redirect(url_for('dashboard'))

    filename = secure_filename(f.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXT:
        flash("Only .py, .js, .zip allowed", "error")
        return redirect(url_for('dashboard'))

    if ext == '.zip':
        return _handle_zip(f, user)
    else:
        return _handle_single(f, user, filename, ext)


def _handle_single(f, user, filename, ext):
    content = f.read()
    if len(content) > MAX_FILE_SIZE:
        flash("File too large", "error")
        return redirect(url_for('dashboard'))

    # Security scan
    try:
        text = content.decode('utf-8', errors='ignore')
        ok, pattern = scan_code(text)
        if not ok:
            flash(f"Security: dangerous pattern detected ({pattern})", "error")
            return redirect(url_for('dashboard'))
    except Exception:
        pass

    sid = db.add_script(user['id'], filename, ext[1:])
    sdir = runner.get_script_dir(user['id'], sid)

    with open(os.path.join(sdir, filename), 'wb') as out:
        out.write(content)

    flash(f"Uploaded '{filename}'. Click Start to run.", "success")
    return redirect(url_for('script_detail', sid=sid))


def _handle_zip(f, user):
    tmp = tempfile.mkdtemp(prefix='zip_')
    try:
        zpath = os.path.join(tmp, 'archive.zip')
        f.save(zpath)

        with zipfile.ZipFile(zpath) as z:
            # Path traversal check
            for member in z.infolist():
                member_path = os.path.abspath(os.path.join(tmp, member.filename))
                if not member_path.startswith(os.path.abspath(tmp)):
                    flash("Unsafe zip path detected", "error")
                    return redirect(url_for('dashboard'))
            z.extractall(tmp)

        # Find main script
        items = os.listdir(tmp)

        # If there's a single folder inside, go into it
        if len(items) == 1 and os.path.isdir(os.path.join(tmp, items[0])):
            tmp = os.path.join(tmp, items[0])
            items = os.listdir(tmp)

        py_files = [x for x in items if x.endswith('.py')]
        js_files = [x for x in items if x.endswith('.js')]

        main = None
        main_type = None

        for pref in ['main.py', 'bot.py', 'app.py', 'server.py', 'run.py']:
            if pref in py_files:
                main, main_type = pref, 'py'
                break

        if not main:
            for pref in ['index.js', 'main.js', 'bot.js', 'app.js', 'server.js']:
                if pref in js_files:
                    main, main_type = pref, 'js'
                    break

        if not main:
            if py_files:
                main, main_type = py_files[0], 'py'
            elif js_files:
                main, main_type = js_files[0], 'js'

        if not main:
            flash("No .py or .js file found in zip", "error")
            return redirect(url_for('dashboard'))

        # Security scan all files
        for root, _, files in os.walk(tmp):
            for fn in files:
                if fn.endswith(('.py', '.js', '.sh')):
                    try:
                        with open(os.path.join(root, fn), 'r', encoding='utf-8', errors='ignore') as fh:
                            ok, pattern = scan_code(fh.read())
                            if not ok:
                                flash(f"Security: {fn} contains dangerous pattern ({pattern})", "error")
                                return redirect(url_for('dashboard'))
                    except Exception:
                        pass

        sid = db.add_script(user['id'], main, main_type)
        sdir = runner.get_script_dir(user['id'], sid)

        # Move all files
        for item in os.listdir(tmp):
            src = os.path.join(tmp, item)
            dst = os.path.join(sdir, item)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)

                # Auto-install deps
        req = os.path.join(sdir, 'requirements.txt')
        pkg = os.path.join(sdir, 'package.json')

        if os.path.exists(req):
            try:
                r = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '-r', req],
                    cwd=sdir, capture_output=True, text=True,
                    encoding='utf-8', errors='ignore', timeout=300
                )
                print(f"[REQ] pip install rc={r.returncode}")
                if r.returncode != 0:
                    print(f"[REQ] STDERR: {r.stderr[:500]}")
            except Exception as e:
                print(f"[REQ] Error installing requirements: {e}")

        if os.path.exists(pkg):
            try:
                r = subprocess.run(
                    ['npm', 'install'], cwd=sdir,
                    capture_output=True, text=True,
                    encoding='utf-8', errors='ignore', timeout=300
                )
                print(f"[NPM] install rc={r.returncode}")
            except Exception as e:
                print(f"[NPM] Error: {e}")

        flash(f"Uploaded zip. Main script: {main}. Click Start.", "success")
        return redirect(url_for('script_detail', sid=sid))

    except zipfile.BadZipFile:
        flash("Invalid zip file", "error")
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f"Error processing zip: {str(e)}", "error")
        return redirect(url_for('dashboard'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.route('/script/<int:sid>')
@login_required
def script_detail(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    status = runner.get_status(sid)
    return render_template('script.html', user=user, script=s, status=status)


@app.route('/script/<int:sid>/start', methods=['POST'])
@login_required
def script_start(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    sdir = runner.get_script_dir(s['user_id'], sid)
    fpath = os.path.join(sdir, s['name'])

    if not os.path.exists(fpath):
        flash("Script file missing", "error")
        return redirect(url_for('script_detail', sid=sid))

    ok, msg = runner.start_script(sid, s['user_id'], fpath, s['type'])
    flash(msg, "success" if ok else "error")
    return redirect(url_for('script_detail', sid=sid))


@app.route('/script/<int:sid>/stop', methods=['POST'])
@login_required
def script_stop(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    ok, msg = runner.stop_script(sid)
    flash(msg, "success" if ok else "error")
    return redirect(url_for('script_detail', sid=sid))


@app.route('/script/<int:sid>/restart', methods=['POST'])
@login_required
def script_restart(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    runner.stop_script(sid)
    sdir = runner.get_script_dir(s['user_id'], sid)
    fpath = os.path.join(sdir, s['name'])

    ok, msg = runner.start_script(sid, s['user_id'], fpath, s['type'])
    flash(msg, "success" if ok else "error")
    return redirect(url_for('script_detail', sid=sid))


@app.route('/script/<int:sid>/delete', methods=['POST'])
@login_required
def script_delete(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    runner.stop_script(sid)
    sdir = runner.get_script_dir(s['user_id'], sid)
    shutil.rmtree(sdir, ignore_errors=True)
    db.delete_script(sid)

    flash("Script deleted", "success")
    return redirect(url_for('dashboard'))


@app.route('/script/<int:sid>/logs')
@login_required
def script_logs(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    log = runner.read_log(sid, s['user_id'])
    status = runner.get_status(sid)
    return jsonify({'log': log, 'status': status})


@app.route('/script/<int:sid>/logs/download')
@login_required
def script_logs_download(sid):
    user = current_user()
    s = db.get_script(sid)

    if not s:
        abort(404)
    if s['user_id'] != user['id'] and not user['is_admin']:
        abort(403)

    sdir = runner.get_script_dir(s['user_id'], sid)
    log_path = os.path.join(sdir, 'output.log')

    if not os.path.exists(log_path):
        abort(404)

    return send_file(log_path, as_attachment=True,
                     download_name=f'script_{sid}.log')


# --- Admin ---
@app.route('/admin')
@admin_required
def admin():
    users = db.list_users()
    user_list = []

    for u in users:
        cnt = db.count_scripts(u['id'])
        running = sum(1 for s in db.list_scripts(u['id']) if runner.is_running(s['id']))
        user_list.append({'user': u, 'file_count': cnt, 'running': running})

    return render_template('admin.html', user=current_user(),
                           users=user_list, total_running=len(runner.RUNNING))


@app.route('/admin/user/<int:uid>/limit', methods=['POST'])
@admin_required
def admin_set_limit(uid):
    try:
        limit = int(request.form.get('limit', 2))
        if limit < 0:
            raise ValueError
        db.update_user_limit(uid, limit)
        flash(f"Limit set to {limit}", "success")
    except Exception:
        flash("Invalid limit", "error")
    return redirect(url_for('admin'))


@app.route('/admin/user/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    if uid == current_user()['id']:
        flash("Can't delete yourself", "error")
        return redirect(url_for('admin'))

    for s in db.list_scripts(uid):
        runner.stop_script(s['id'])

    db.delete_user(uid)
    shutil.rmtree(os.path.join(UPLOAD_DIR, str(uid)), ignore_errors=True)

    flash("User deleted", "success")
    return redirect(url_for('admin'))


# --- CLI: make-admin ---
def ensure_admin():
    """Run: python app.py make-admin <username>"""
    if len(sys.argv) >= 3 and sys.argv[1] == 'make-admin':
        uname = sys.argv[2]
        u = db.get_user_by_username(uname)
        if not u:
            print(f"No user '{uname}'")
            sys.exit(1)

        conn = db.get_db()
        conn.execute('UPDATE users SET is_admin=1 WHERE id=?', (u['id'],))
        conn.commit()
        conn.close()

        print(f"✅ '{uname}' is now admin")
        sys.exit(0)


# --- Cleanup on exit ---
import atexit
atexit.register(runner.cleanup_all)


# --- Main ---
if __name__ == '__main__':
    ensure_admin()
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting PyHost on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
