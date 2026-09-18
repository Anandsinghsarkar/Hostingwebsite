# -*- coding: utf-8 -*-
import os, sys, re, zipfile, tempfile, shutil, subprocess, uuid
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, abort, send_file)
from werkzeug.utils import secure_filename

import db
import runner
from firebase_config import init_firebase
from firebase_admin import auth as fb_auth

# --- Config ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXT = {'.py', '.js', '.zip'}
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Init Firebase
init_firebase()

# Firebase Web config (client-side)
FIREBASE_WEB_CONFIG = {
    'apiKey': os.environ.get('FB_API_KEY', ''),
    'authDomain': os.environ.get('FB_AUTH_DOMAIN', ''),
    'projectId': os.environ.get('FB_PROJECT_ID', ''),
    'storageBucket': os.environ.get('FB_STORAGE_BUCKET', ''),
    'messagingSenderId': os.environ.get('FB_SENDER_ID', ''),
    'appId': os.environ.get('FB_APP_ID', ''),
}


# --- Auth helpers ---
def verify_token(id_token):
    try:
        return fb_auth.verify_id_token(id_token)
    except Exception as e:
        print(f"Token verify failed: {e}")
        return None


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    u = db.get_user(uid)
    if not u:
        return None
    u['uid'] = uid
    return u


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not current_user():
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        u = current_user()
        if not u or not u.get('is_admin'):
            abort(403)
        return f(*a, **kw)
    return w


# --- Security scan ---
DANGEROUS = [
    r'rm\s+-rf\s+/',
    r'\bos\.system\s*\(',
    r'\bos\.popen\s*\(',
    r'subprocess\.(Popen|call|run)\s*\([^)]*shell\s*=\s*True',
    r'\bctypes\b',
    r'__import__\s*\(\s*[\'"]os[\'"]\s*\)',
    r'shutil\.rmtree\s*\(\s*[\'"]/',
]


def scan_code(text):
    for pat in DANGEROUS:
        if re.search(pat, text):
            return False, pat
    return True, None


# ========== ROUTES ==========

@app.route('/')
def index():
    if current_user():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/login')
def login():
    if current_user():
        return redirect(url_for('dashboard'))
    return render_template('login.html', fb_config=FIREBASE_WEB_CONFIG)


@app.route('/auth/session', methods=['POST'])
def auth_session():
    data = request.get_json() or {}
    id_token = data.get('idToken')
    if not id_token:
        return jsonify({'ok': False, 'error': 'No token'}), 400

    claims = verify_token(id_token)
    if not claims:
        return jsonify({'ok': False, 'error': 'Invalid token'}), 401

    uid = claims['uid']
    email = claims.get('email', '')
    name = claims.get('name', email.split('@')[0] if email else 'User')
    picture = claims.get('picture', '')

    user = db.create_or_update_user(uid, email, name, picture)
    session['uid'] = uid

    return jsonify({'ok': True, 'is_admin': user.get('is_admin', False)})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    scripts = db.list_scripts(user['uid'])
    for s in scripts:
        s['status'] = runner.get_status(s['id'])
        s['running'] = s['status'].get('running', False)
    running_count = sum(1 for s in scripts if s['running'])
    total_users = db.count_users()
    return render_template('dashboard.html', user=user, scripts=scripts,
                           running_count=running_count, total_users=total_users,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/my-bots')
@login_required
def my_bots():
    user = current_user()
    scripts = db.list_scripts(user['uid'])
    for s in scripts:
        s['status'] = runner.get_status(s['id'])
        s['running'] = s['status'].get('running', False)
    return render_template('my_bots.html', user=user, scripts=scripts,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/create-bot')
@login_required
def create_bot():
    user = current_user()
    return render_template('create_bot.html', user=user,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    user = current_user()
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'No file'}), 400

    if db.count_scripts(user['uid']) >= user.get('file_limit', 2):
        return jsonify({'ok': False, 'error': f"File limit reached"}), 400

    filename = secure_filename(f.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'ok': False, 'error': 'Only .py, .js, .zip'}), 400

    sid = str(uuid.uuid4())[:12]
    sdir = runner.get_script_dir(user['uid'], sid)
    os.makedirs(sdir, exist_ok=True)

    if ext == '.zip':
        return _handle_zip(f, user, sid, sdir)
    return _handle_single(f, user, sid, sdir, filename, ext)


def _handle_single(f, user, sid, sdir, filename, ext):
    content = f.read()
    if len(content) > MAX_FILE_SIZE:
        return jsonify({'ok': False, 'error': 'Too large'}), 400
    try:
        text = content.decode('utf-8', errors='ignore')
        ok, pat = scan_code(text)
        if not ok:
            return jsonify({'ok': False, 'error': f'Dangerous: {pat}'}), 400
    except Exception:
        pass

    with open(os.path.join(sdir, filename), 'wb') as out:
        out.write(content)

    db.add_script(sid, user['uid'], filename, ext[1:], sdir)
    return jsonify({'ok': True, 'sid': sid})


def _handle_zip(f, user, sid, sdir):
    tmp = tempfile.mkdtemp(prefix='zip_')
    try:
        zpath = os.path.join(tmp, 'archive.zip')
        f.save(zpath)
        with zipfile.ZipFile(zpath) as z:
            for m in z.infolist():
                p = os.path.abspath(os.path.join(tmp, m.filename))
                if not p.startswith(os.path.abspath(tmp)):
                    return jsonify({'ok': False, 'error': 'Unsafe zip'}), 400
            z.extractall(tmp)

        items = os.listdir(tmp)
        if len(items) == 1 and os.path.isdir(os.path.join(tmp, items[0])):
            tmp = os.path.join(tmp, items[0])
            items = os.listdir(tmp)

        py = [x for x in items if x.endswith('.py')]
        js = [x for x in items if x.endswith('.js')]
        main, main_type = None, None
        for p in ['main.py', 'bot.py', 'app.py', 'server.py', 'run.py']:
            if p in py:
                main, main_type = p, 'py'; break
        if not main:
            for p in ['index.js', 'main.js', 'bot.js', 'app.js']:
                if p in js:
                    main, main_type = p, 'js'; break
        if not main:
            if py: main, main_type = py[0], 'py'
            elif js: main, main_type = js[0], 'js'
        if not main:
            return jsonify({'ok': False, 'error': 'No .py/.js found'}), 400

        # Security scan
        for root, _, files in os.walk(tmp):
            for fn in files:
                if fn.endswith(('.py', '.js', '.sh')):
                    try:
                        with open(os.path.join(root, fn), 'r', encoding='utf-8', errors='ignore') as fh:
                            ok, pat = scan_code(fh.read())
                            if not ok:
                                return jsonify({'ok': False, 'error': f'{fn}: {pat}'}), 400
                    except Exception:
                        pass

        # Move files
        for item in os.listdir(tmp):
            src = os.path.join(tmp, item)
            dst = os.path.join(sdir, item)
            if os.path.isdir(dst): shutil.rmtree(dst)
            elif os.path.exists(dst): os.remove(dst)
            shutil.move(src, dst)

        # Auto-install deps
        req = os.path.join(sdir, 'requirements.txt')
        if os.path.exists(req):
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install',
                                '--no-cache-dir', '-r', req],
                               cwd=sdir, capture_output=True, timeout=300)
            except Exception:
                pass

        db.add_script(sid, user['uid'], main, main_type, sdir)
        return jsonify({'ok': True, 'sid': sid})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.route('/api/script/<sid>/start', methods=['POST'])
@login_required
def api_start(sid):
    user = current_user()
    s = db.get_script(sid)
    if not s: return jsonify({'ok': False, 'error': 'Not found'}), 404
    if s['user_id'] != user['uid'] and not user.get('is_admin'):
        return jsonify({'ok': False, 'error': 'Forbidden'}), 403

    sdir = runner.get_script_dir(s['user_id'], sid)
    fpath = os.path.join(sdir, s['name'])
    if not os.path.exists(fpath):
        return jsonify({'ok': False, 'error': 'File missing'}), 400

    ok, msg = runner.start_script(sid, s['user_id'], fpath, s['type'])
    if ok: db.update_script(sid, {'running': True})
    return jsonify({'ok': ok, 'message': msg})


@app.route('/api/script/<sid>/stop', methods=['POST'])
@login_required
def api_stop(sid):
    user = current_user()
    s = db.get_script(sid)
    if not s: return jsonify({'ok': False}), 404
    if s['user_id'] != user['uid'] and not user.get('is_admin'):
        return jsonify({'ok': False}), 403

    ok, msg = runner.stop_script(sid)
    if ok: db.update_script(sid, {'running': False})
    return jsonify({'ok': ok, 'message': msg})


@app.route('/api/script/<sid>/logs')
@login_required
def api_logs(sid):
    user = current_user()
    s = db.get_script(sid)
    if not s: return jsonify({'ok': False}), 404
    if s['user_id'] != user['uid'] and not user.get('is_admin'):
        return jsonify({'ok': False}), 403
    log = runner.read_log(sid, s['user_id'])
    status = runner.get_status(sid)
    return jsonify({'ok': True, 'log': log, 'status': status})


@app.route('/api/script/<sid>/delete', methods=['POST'])
@login_required
def api_delete(sid):
    user = current_user()
    s = db.get_script(sid)
    if not s: return jsonify({'ok': False}), 404
    if s['user_id'] != user['uid'] and not user.get('is_admin'):
        return jsonify({'ok': False}), 403
    runner.stop_script(sid)
    sdir = runner.get_script_dir(s['user_id'], sid)
    shutil.rmtree(sdir, ignore_errors=True)
    db.delete_script(sid)
    return jsonify({'ok': True})


@app.route('/pricing')
def pricing():
    user = current_user()
    return render_template('pricing.html', user=user,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/docs')
def docs():
    user = current_user()
    return render_template('docs.html', user=user,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/support')
def support():
    user = current_user()
    return render_template('support.html', user=user,
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/payment-history')
@login_required
def payment_history():
    user = current_user()
    payments = db.list_payments(user['uid'])
    return render_template('payment_history.html', user=user, payments=payments,
                           fb_config=FIREBASE_WEB_CONFIG)


# ========== ADMIN ==========

@app.route('/admin')
@admin_required
def admin_dashboard():
    user = current_user()
    users = db.list_users()
    scripts = db.list_scripts()
    for u in users:
        u['script_count'] = db.count_scripts(u['uid'])
    for s in scripts:
        s['status'] = runner.get_status(s['id'])
        s['running'] = s['status'].get('running', False)
    return render_template('admin.html', user=user, users=users, scripts=scripts,
                           running_count=sum(1 for s in scripts if s['running']),
                           fb_config=FIREBASE_WEB_CONFIG)


@app.route('/admin/user/<uid>/limit', methods=['POST'])
@admin_required
def admin_set_limit(uid):
    try:
        limit = int(request.form.get('limit', 2))
        db.set_user_limit(uid, limit)
        flash(f"Limit set to {limit}", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<uid>/plan', methods=['POST'])
@admin_required
def admin_set_plan(uid):
    plan = request.form.get('plan', 'free')
    db.set_user_plan(uid, plan)
    flash(f"Plan set to {plan}", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<uid>/admin', methods=['POST'])
@admin_required
def admin_toggle_admin(uid):
    val = request.form.get('is_admin') == '1'
    db.make_admin(uid, val)
    flash(f"Admin: {val}", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    if uid == current_user()['uid']:
        flash("Can't delete yourself", "error")
        return redirect(url_for('admin_dashboard'))
    for s in db.list_scripts(uid):
        runner.stop_script(s['id'])
    shutil.rmtree(os.path.join(UPLOAD_DIR, uid), ignore_errors=True)
    db.delete_user(uid)
    flash("User deleted", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/payments')
@admin_required
def admin_payments():
    user = current_user()
    payments = db.list_payments()
    users_list = db.list_users()
    users_map = {u['uid']: u for u in users_list}
    return render_template('admin_payments.html', user=user, payments=payments,
                           users=users_map, fb_config=FIREBASE_WEB_CONFIG)


@app.route('/admin/payment/add', methods=['POST'])
@admin_required
def admin_add_payment():
    try:
        user_id = request.form['user_id']
        amount = request.form['amount']
        method = request.form.get('method', 'manual')
        status = request.form.get('status', 'success')
        note = request.form.get('note', '')
        db.add_payment(user_id, amount, method, status, note)
        flash("Payment added", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for('admin_payments'))


@app.route('/admin/script/<sid>/start', methods=['POST'])
@admin_required
def admin_start(sid):
    s = db.get_script(sid)
    if not s: return jsonify({'ok': False}), 404
    sdir = runner.get_script_dir(s['user_id'], sid)
    fpath = os.path.join(sdir, s['name'])
    if not os.path.exists(fpath):
        return jsonify({'ok': False, 'error': 'File missing'}), 400
    ok, msg = runner.start_script(sid, s['user_id'], fpath, s['type'])
    return jsonify({'ok': ok, 'message': msg})


@app.route('/admin/script/<sid>/stop', methods=['POST'])
@admin_required
def admin_stop(sid):
    ok, msg = runner.stop_script(sid)
    return jsonify({'ok': ok, 'message': msg})


# --- Cleanup on exit ---
import atexit
atexit.register(runner.cleanup_all)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
