"""
Script process manager — subprocess.Popen based.
Har script ka apna process + log file hoti hai.
"""
import os, sys, subprocess, threading, time
from datetime import datetime
import psutil

# {script_id: {'proc': Popen, 'log_file': file, 'start_time': datetime, 'user_id': int, 'name': str}}
RUNNING = {}
LOCK = threading.Lock()


def get_script_dir(user_id, script_id):
    from app import UPLOAD_DIR
    d = os.path.join(UPLOAD_DIR, str(user_id), str(script_id))
    os.makedirs(d, exist_ok=True)
    return d


def is_running(script_id):
    with LOCK:
        info = RUNNING.get(script_id)
        if not info:
            return False
        proc = info['proc']
        try:
            p = psutil.Process(proc.pid)
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                _cleanup(script_id)
                return False
            return True
        except psutil.NoSuchProcess:
            _cleanup(script_id)
            return False


def _cleanup(script_id):
    info = RUNNING.pop(script_id, None)
    if info and info.get('log_file'):
        try:
            if not info['log_file'].closed:
                info['log_file'].close()
        except Exception:
            pass


def start_script(script_id, user_id, file_path, file_type):
    """
    Start a script. Returns (ok, message).
    file_type: 'py' or 'js'
    """
    if is_running(script_id):
        return False, "Script already running"

    script_dir = get_script_dir(user_id, script_id)
    log_path = os.path.join(script_dir, 'output.log')
    log_file = open(log_path, 'a', encoding='utf-8', errors='ignore')

    cmd = [sys.executable, file_path] if file_type == 'py' else ['node', file_path]

    try:
        # Pre-check for missing modules
        ok, missing = _precheck(cmd, script_dir)
        if not ok and missing:
            log_file.write(f"[SYSTEM] Installing missing module: {missing}\n")
            installed = _auto_install(missing, file_type, script_dir, user_id)
            if not installed:
                log_file.write(f"[SYSTEM] Auto-install failed for {missing}\n")
                log_file.close()
                return False, f"Missing module '{missing}' and auto-install failed"

        # Linux: new session so we can kill process group later
        kwargs = {}
        if os.name != 'nt':
            kwargs['start_new_session'] = True
        else:
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            cmd,
            cwd=script_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **kwargs
        )

        with LOCK:
            RUNNING[script_id] = {
                'proc': proc,
                'log_file': log_file,
                'start_time': datetime.now(),
                'user_id': user_id,
                'type': file_type,
            }
        return True, f"Started (PID: {proc.pid})"
    except FileNotFoundError as e:
        log_file.close()
        return False, f"Executable not found: {e}"
    except Exception as e:
        log_file.close()
        return False, f"Error: {e}"


def stop_script(script_id):
    with LOCK:
        info = RUNNING.get(script_id)
    if not info:
        return False, "Not running"

    pid = info['proc'].pid
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for ch in children:
            try: ch.terminate()
            except Exception: pass
        try: parent.terminate()
        except Exception: pass

        gone, alive = psutil.wait_procs([parent] + children, timeout=3)
        for p in alive:
            try: p.kill()
            except Exception: pass
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        return False, f"Error stopping: {e}"
    finally:
        _cleanup(script_id)
    return True, "Stopped"


def get_status(script_id):
    if not is_running(script_id):
        return {'running': False}
    info = RUNNING[script_id]
    proc = info['proc']
    try:
        p = psutil.Process(proc.pid)
        mem = p.memory_info().rss / 1024 / 1024
        cpu = p.cpu_percent(interval=0.1)
    except Exception:
        mem, cpu = 0, 0
    uptime = int((datetime.now() - info['start_time']).total_seconds())
    return {
        'running': True,
        'pid': proc.pid,
        'uptime': uptime,
        'memory_mb': round(mem, 2),
        'cpu': cpu,
    }


def read_log(script_id, user_id, tail_kb=100):
    """Read last N KB of log file."""
    script_dir = get_script_dir(user_id, script_id)
    log_path = os.path.join(script_dir, 'output.log')
    if not os.path.exists(log_path):
        return "(No log yet)"
    size = os.path.getsize(log_path)
    with open(log_path, 'rb') as f:
        if size > tail_kb * 1024:
            f.seek(-tail_kb * 1024, os.SEEK_END)
        data = f.read()
    return data.decode('utf-8', errors='ignore')


# --- Auto dependency detection & install ---
def _precheck(cmd, cwd):
    """Quickly run script; if it crashes with ModuleNotFound, return module name."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding='utf-8', errors='ignore', timeout=5)
        if r.returncode != 0 and r.stderr:
            import re
            m = re.search(r"No module named '([^']+)'", r.stderr)
            if m:
                return False, m.group(1).split('.')[0]
            m = re.search(r"Cannot find module '([^']+)'", r.stderr)
            if m:
                return False, m.group(1)
        return True, None
    except subprocess.TimeoutExpired:
        return True, None  # started fine, timed out on its own
    except Exception:
        return True, None


def _auto_install(module, file_type, cwd, user_id):
    from db import log_install
    try:
        if file_type == 'py':
            cmd = [sys.executable, '-m', 'pip', 'install', module]
        else:
            cmd = ['npm', 'install', module]
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding='utf-8', errors='ignore', timeout=120)
        status = 'success' if r.returncode == 0 else 'failed'
        log_install(user_id, module, status, (r.stdout or '') + '\n' + (r.stderr or ''))
        return r.returncode == 0
    except Exception as e:
        log_install(user_id, module, 'error', str(e))
        return False


def cleanup_all():
    for sid in list(RUNNING.keys()):
        stop_script(sid)