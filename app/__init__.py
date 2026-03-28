import os
from flask import Flask
from pymongo import MongoClient
from config import Config

mongo_client = None
mongo_db = None


def create_app():
    global mongo_client, mongo_db

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    mongo_client = MongoClient(app.config["MONGO_URI"])
    mongo_db = mongo_client.get_default_database()

    from app.routes import main
    app.register_blueprint(main)

    return app