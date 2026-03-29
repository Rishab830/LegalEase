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