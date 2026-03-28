import os
import importlib
from pymongo import MongoClient
from app import create_app


REQUIRED_CONFIG_KEYS = ["SECRET_KEY", "MONGO_URI", "UPLOAD_FOLDER"]
REQUIRED_IMPORTS = [
    "flask",
    "pymongo",
    "dotenv",
    "flask_login",
    "PIL",
    "pytesseract",
    "pdfplumber"
]


def test_app_creation():
    app = create_app()
    assert app is not None
    print("PASS: Flask app created")


def test_config_values():
    app = create_app()
    for key in REQUIRED_CONFIG_KEYS:
        value = app.config.get(key)
        assert value is not None and str(value).strip() != "", f"{key} is missing"
    print("PASS: Config values present")


def test_upload_folder():
    app = create_app()
    upload_folder = app.config["UPLOAD_FOLDER"]
    assert os.path.exists(upload_folder), "Upload folder does not exist"
    test_file = os.path.join(upload_folder, "test_write.tmp")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("ok")
    assert os.path.exists(test_file), "Upload folder is not writable"
    os.remove(test_file)
    print("PASS: Upload folder exists and is writable")


def test_mongodb_connection():
    app = create_app()
    client = MongoClient(app.config["MONGO_URI"])
    result = client.admin.command("ping")
    assert result.get("ok") == 1.0, "MongoDB ping failed"
    print("PASS: MongoDB connection successful")


def test_required_imports():
    for module_name in REQUIRED_IMPORTS:
        importlib.import_module(module_name)
    print("PASS: All required packages import successfully")


if __name__ == "__main__":
    test_app_creation()
    test_config_values()
    test_upload_folder()
    test_mongodb_connection()
    test_required_imports()
    print("\nALL SETUP TESTS PASSED")