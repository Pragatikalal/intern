import os

BASE = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    DATABASE = os.path.join(BASE, "instance", "energy.db")
    UPLOAD_FOLDER = os.path.join(BASE, "uploads")
    MODEL_FOLDER = os.path.join(BASE, "models")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024      # 10 MB upload cap
    ALLOWED_EXTENSIONS = {"csv"}
    MAX_UPLOAD_ROWS = 200_000
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
