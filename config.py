import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-this")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://rishabrnair05_db_user:<db_password>@legalease.unjapn5.mongodb.net/?appName=LegalEase")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")