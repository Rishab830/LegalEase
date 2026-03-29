import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-this")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://rishabrnair05_db_user:<db_password>@legalease.unjapn5.mongodb.net/?appName=LegalEase")
    _default_upload = os.getenv("UPLOAD_FOLDER", "uploads")
    UPLOAD_FOLDER = _default_upload if os.path.isabs(_default_upload) else os.path.join(basedir, _default_upload)
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Flask-Mail configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@legalease.com")