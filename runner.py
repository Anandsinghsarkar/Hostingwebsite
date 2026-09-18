# -*- coding: utf-8 -*-
"""
Script process manager — subprocess.Popen based.
Har script ka apna process + log file hoti hai.
"""
import os
import sys
import re
import subprocess
import threading
import time
from datetime import datetime

import psutil


# --- Module name → PyPI package mapping ---
# Ye zaroori hai kyunki bahut libraries ka import name PyPI naam se alag hota hai
PACKAGE_MAP = {
    # ===== Telegram libraries =====
    'telegram': 'python-telegram-bot',
    'telebot': 'pyTelegramBotAPI',
    'telegram_ext': 'python-telegram-bot',
    'telegram_utils': 'telegram-utils',
    'pyrogram': 'pyrogram',
    'aiogram': 'aiogram',
    'telethon': 'telethon',
    'tgcrypto': 'TgCrypto',
    'telepot': 'telepot',

    # ===== Common import↔package differences =====
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'pillow': 'Pillow',
    'bs4': 'beautifulsoup4',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'sklearn': 'scikit-learn',
    'skimage': 'scikit-image',
    'serial': 'pyserial',
    'Crypto': 'pycryptodome',
    'jwt': 'PyJWT',
    'dateutil': 'python-dateutil',
    'flask_cors': 'flask-cors',
    'flask_sqlalchemy': 'flask-sqlalchemy',
    'flask_login': 'flask-login',
    'flask_limiter': 'flask-limiter',
    'mysql': 'mysql-connector-python',
    'psycopg2': 'psycopg2-binary',
    'discord': 'discord.py',
    'google.generativeai': 'google-generativeai',
    'google': 'google',
    'gtts': 'gTTS',
    'pydub': 'pydub',
    'moviepy': 'moviepy',
    'yt_dlp': 'yt-dlp',
    'pytube': 'pytube',
    'googlesearch': 'googlesearch-python',
    'speech_recognition': 'SpeechRecognition',
    'pyaudio': 'PyAudio',
    'docx': 'python-docx',
    'pptx': 'python-pptx',
    'openpyxl': 'openpyxl',
    'fpdf': 'fpdf2',
    'qrcode': 'qrcode',
    'pytz': 'pytz',
    'win32api': 'pywin32',
    'win32com': 'pywin32',
    'wx': 'wxPython',
    'PyQt5': 'PyQt5',
    'PyQt6': 'PyQt6',
    'PySide2': 'PySide2',
    'PySide6': 'PySide6',
    'plotly': 'plotly',
    'seaborn': 'seaborn',
    'tensorflow': 'tensorflow',
    'torch': 'torch',
    'keras': 'keras',
    'transformers': 'transformers',
    'langchain': 'langchain',
    'openai': 'openai',
    'anthropic': 'anthropic',
    'cohere': 'cohere',
    'whisper': 'openai-whisper',
    'xgboost': 'xgboost',
    'lightgbm': 'lightgbm',
    'catboost': 'catboost',
    'xgboost': 'xgboost',
    'nltk': 'nltk',
    'spacy': 'spacy',
    'gensim': 'gensim',
    'scrapy': 'Scrapy',
    'selenium': 'selenium',
    'playwright': 'playwright',
    'boto3': 'boto3',
    'google.cloud': 'google-cloud-storage',
    'azure': 'azure-storage-blob',
    'instagrapi': 'instagrapi',
    'instaloader': 'instaloader',
    'tweepy': 'tweepy',
    'praw': 'praw',
    'wikipedia': 'wikipedia',
    'mtranslate': 'mtranslate',
    'googletrans': 'googletrans==4.0.0-rc1',
    'deep_translator': 'deep-translator',
}


# --- Core Python modules — install nahi karne ---
CORE_MODULES = {
    # Builtins
    'os', 'sys', 're', 'json', 'time', 'datetime', 'math', 'random',
    'logging', 'threading', 'subprocess', 'asyncio', 'collections',
    'itertools', 'functools', 'typing', 'pathlib', 'io', 'socket',
    'base64', 'hashlib', 'hmac', 'secrets', 'uuid', 'sqlite3',
    'urllib', 'http', 'email', 'zipfile', 'tempfile', 'shutil',
    'pickle', 'csv', 'xml', 'html', 'unittest', 'dataclasses',
    'traceback', 'warnings', 'contextlib', 'abc', 'copy', 'enum',
    'glob', 'signal', 'atexit', 'platform', 'statistics',
    'argparse', 'ast', 'binascii', 'bisect', 'calendar', 'cmath',
    'codecs', 'concurrent', 'configparser', 'contextvars', 'crypt',
    'ctypes', 'curses', 'decimal', 'difflib', 'dis', 'doctest',
    'errno', 'faulthandler', 'filecmp', 'fileinput', 'fnmatch',
    'fractions', 'ftplib', 'gc', 'getopt', 'getpass', 'gettext',
    'graphlib', 'gzip', 'heapq', 'imaplib', 'imp', 'importlib',
    'inspect', 'ipaddress', 'keyword', 'linecache', 'locale',
    'lzma', 'mailbox', 'marshal', 'mimetypes', 'mmap', 'multiprocessing',
    'netrc', 'numbers', 'operator', 'optparse', 'os.path', 'pdb',
    'pickletools', 'pkgutil', 'platform', 'plistlib', 'poplib',
    'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile',
    'queue', 'quopri', 'select', 'selectors', 'shelve', 'shlex',
    'site', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'sqlite3',
    'ssl', 'stat', 'string', 'stringprep', 'struct', 'symtable',
    'tabnanny', 'tarfile', 'telnetlib', 'textwrap', 'timeit',
    'tkinter', 'token', 'tokenize', 'trace', 'tracemalloc',
    'tty', 'turtle', 'types', 'unicodedata', 'uu', 'venv',
    'wave', 'weakref', 'webbrowser', 'wsgiref', 'xdrlib',
    'xmlrpc', 'zipapp', 'zlib', 'zoneinfo',
}


# --- Global state ---
RUNNING = {}  # {script_id: {'proc': Popen, 'log_file': file, 'start_time': datetime, 'user_id': int, 'type': str}}
LOCK = threading.Lock()


def get_script_dir(user_id, script_id):
    """Get/create the script working directory."""
    # Import here to avoid circular import
    from app import UPLOAD_DIR
    d = os.path.join(UPLOAD_DIR, str(user_id), str(script_id))
    os.makedirs(d, exist_ok=True)
    return d


def is_running(script_id):
    """Check if script process is alive."""
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
        except Exception:
            _cleanup(script_id)
            return False


def _cleanup(script_id):
    """Close log file and remove from RUNNING."""
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

    # Rotate log if too big (>2MB)
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > 2 * 1024 * 1024:
            os.remove(log_path)
    except Exception:
        pass

    log_file = open(log_path, 'a', encoding='utf-8', errors='ignore')

    cmd = [sys.executable, file_path] if file_type == 'py' else ['node', file_path]

    # --- Pre-check for missing modules ---
    log_file.write(f"\n\n===== Starting {datetime.now().isoformat()} =====\n")
    log_file.flush()

    try:
        missing = _precheck(cmd, script_dir, log_file)

        if missing:
            # Try to auto-install
            log_file.write(f"[SYSTEM] Detected missing module: {missing}\n")
            log_file.flush()

            ok = _auto_install(missing, file_type, script_dir, user_id, log_file)

            if not ok:
                log_file.write(f"[SYSTEM] Auto-install FAILED for '{missing}'. Aborting.\n")
                log_file.flush()
                log_file.close()
                return False, f"Missing module '{missing}' — auto-install failed. Add requirements.txt."

            log_file.write(f"[SYSTEM] Auto-install success for '{missing}'. Retrying...\n")
            log_file.flush()

            # Retry precheck once more after install
            missing2 = _precheck(cmd, script_dir, log_file)
            if missing2:
                log_file.write(f"[SYSTEM] Still missing after install: '{missing2}'.\n")
                log_file.flush()
                log_file.close()
                return False, f"Still missing '{missing2}' after install"

    except Exception as e:
        log_file.write(f"[SYSTEM] Precheck error: {e}\n")
        log_file.flush()
        # Continue anyway — maybe script will work

    # --- Start long-running process ---
    try:
        kwargs = {}
        if os.name != 'nt':
            kwargs['start_new_session'] = True  # Linux/Mac: new process group
        else:
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP  # Windows

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
    """Kill script and its children."""
    with LOCK:
        info = RUNNING.get(script_id)

    if not info:
        return False, "Not running"

    pid = info['proc'].pid

    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        # Graceful terminate first
        for ch in children:
            try:
                ch.terminate()
            except Exception:
                pass
        try:
            parent.terminate()
        except Exception:
            pass

        # Wait up to 3 seconds
        gone, alive = psutil.wait_procs([parent] + children, timeout=3)

        # Force kill anything still alive
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass

    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        return False, f"Error stopping: {e}"
    finally:
        _cleanup(script_id)

    return True, "Stopped"


def get_status(script_id):
    """Get running status + resource usage."""
    if not is_running(script_id):
        return {'running': False}

    with LOCK:
        info = RUNNING.get(script_id)

    if not info:
        return {'running': False}

    proc = info['proc']
    try:
        p = psutil.Process(proc.pid)
        mem = p.memory_info().rss / 1024 / 1024  # MB
        cpu = p.cpu_percent(interval=0.1)
    except Exception:
        mem, cpu = 0, 0

    uptime = int((datetime.now() - info['start_time']).total_seconds())

    return {
        'running': True,
        'pid': proc.pid,
        'uptime': uptime,
        'memory_mb': round(mem, 2),
        'cpu': round(cpu, 2),
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
def _resolve_package_name(module):
    """Convert import name to correct PyPI package name. Returns None for core modules."""
    module = module.split('.')[0]  # 'telegram.ext' → 'telegram'
    if module in CORE_MODULES:
        return None
    return PACKAGE_MAP.get(module, module)


def _precheck(cmd, cwd, log_file=None):
    """
    Run script briefly. If it crashes with missing module, return module name.
    Returns: module_name (str) or None
    """
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=8  # 8 seconds
        )

        if r.returncode != 0 and r.stderr:
            stderr = r.stderr

            # --- Python: ModuleNotFoundError ---
            m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", stderr)
            if m:
                module = m.group(1).split('.')[0]
                if module in CORE_MODULES:
                    return None  # can't install core
                return module

            # --- Python: ImportError from X (partial installs) ---
            m = re.search(r"ImportError: cannot import name .+ from '([^']+)'", stderr)
            if m:
                module = m.group(1).split('.')[0]
                if module in CORE_MODULES:
                    return None
                return module

            # --- Node.js: Cannot find module ---
            m = re.search(r"Cannot find module '([^']+)'", stderr)
            if m:
                mod = m.group(1)
                if not mod.startswith('.') and not mod.startswith('/'):
                    return mod

        return None

    except subprocess.TimeoutExpired:
        # Script ran longer than 8s → imports OK, it's a long-running bot
        return None
    except FileNotFoundError as e:
        if log_file:
            log_file.write(f"[SYSTEM] Executable not found: {e}\n")
            log_file.flush()
        return None
    except Exception as e:
        if log_file:
            log_file.write(f"[SYSTEM] Precheck exception: {e}\n")
            log_file.flush()
        return None


def _auto_install(module, file_type, cwd, user_id, log_file=None):
    """Install missing module. Returns True/False."""
    from db import log_install

    package = _resolve_package_name(module)

    if package is None:
        if log_file:
            log_file.write(f"[SYSTEM] '{module}' is a core module, skipping install.\n")
            log_file.flush()
        return False

    try:
        if file_type == 'py':
            cmd = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', package]
        else:
            cmd = ['npm', 'install', module]

        if log_file:
            log_file.write(f"[SYSTEM] Running: {' '.join(cmd)}\n")
            log_file.flush()

        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=180  # 3 minutes max
        )

        status = 'success' if r.returncode == 0 else 'failed'
        full_log = f"$ {' '.join(cmd)}\n\nSTDOUT:\n{r.stdout or ''}\n\nSTDERR:\n{r.stderr or ''}"
        log_install(user_id, f"{module} → {package}", status, full_log)

        if log_file:
            if r.returncode == 0:
                log_file.write(f"[SYSTEM] ✅ Installed '{package}' successfully.\n")
            else:
                log_file.write(f"[SYSTEM] ❌ Install failed for '{package}'.\n")
                if r.stderr:
                    log_file.write(f"[SYSTEM] Error: {r.stderr[:500]}\n")
            log_file.flush()

        return r.returncode == 0

    except subprocess.TimeoutExpired:
        log_install(user_id, module, 'timeout', 'Installation timed out after 180s')
        if log_file:
            log_file.write(f"[SYSTEM] ⏱️ Install timeout for '{package}'.\n")
            log_file.flush()
        return False
    except FileNotFoundError:
        log_install(user_id, module, 'error', 'pip/npm not found in PATH')
        if log_file:
            log_file.write(f"[SYSTEM] ❌ pip/npm not found.\n")
            log_file.flush()
        return False
    except Exception as e:
        log_install(user_id, module, 'error', str(e))
        if log_file:
            log_file.write(f"[SYSTEM] ❌ Install exception: {e}\n")
            log_file.flush()
        return False


def cleanup_all():
    """Kill all running scripts on shutdown."""
    for sid in list(RUNNING.keys()):
        try:
            stop_script(sid)
        except Exception:
            pass
