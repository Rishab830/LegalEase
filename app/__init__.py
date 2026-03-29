import os
from flask import Flask
from pymongo import MongoClient
from config import Config
from flask_login import LoginManager

mongo_client = None
mongo_db = None


def create_app():
    global mongo_client, mongo_db

    # Get the root directory (parent of app directory)
    root_dir = os.path.dirname(os.path.dirname(__file__))
    
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static")
    )
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    mongo_client = MongoClient(app.config["MONGO_URI"])
    # Use 'legalease' as fallback if no database is specified in the URI
    mongo_db = mongo_client.get_default_database('legalease')
    
    # Store mongo_db in app config for access in app context
    app.config['mongo_db'] = mongo_db

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    from app.routes import main
    app.register_blueprint(main)

    from app.auth import auth
    app.register_blueprint(auth)

    return app