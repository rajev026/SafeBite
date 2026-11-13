import os
import shutil
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Always load .env from the application directory regardless of CWD
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.path.join(BASE_DIR, "safebite.db")
OUTBOX_DIR = os.path.join(BASE_DIR, "outbox")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "16"))
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "bmp"}

def _detect_tesseract():
    env_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd
    candidates = [
        r"D:\Apps\tesseract\tesseract.exe",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        shutil.which("tesseract"),
        shutil.which("tesseract.exe"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return env_cmd

TESSERACT_CMD = _detect_tesseract()
OCR_LOW_CONF = 60          # words below this confidence are underlined in the UI

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

OFF_BASE = "https://world.openfoodfacts.org"
OFF_HEADERS = {"User-Agent": "SafeBite/1.0 (python hackathon project)"}
