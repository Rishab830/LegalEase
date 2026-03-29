import os
from flask import Flask
from pymongo import MongoClient
from config import Config
from flask_login import LoginManager
from app.extensions import mail, mongo_client, mongo_db


def create_app(config_object=None):
    # Need to declare as global to modify them inside create_app
    global mongo_client, mongo_db

    # Get the root directory (parent of app directory)
    root_dir = os.path.dirname(os.path.dirname(__file__))
    
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static")
    )
    app.config.from_object(Config)
    if config_object:
        app.config.update(config_object)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    mongo_client = MongoClient(app.config["MONGO_URI"])
    # Use 'legalease' as fallback if no database is specified in the URI
    mongo_db = mongo_client.get_default_database('legalease')
    
    # Store mongo_db in app config for access in app context
    app.config['mongo_db'] = mongo_db

    # Initialize Flask-Mail
    mail.init_app(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.models import User, Notification

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    @app.context_processor
    def inject_unread_count():
        from flask_login import current_user
        if current_user.is_authenticated:
            return {'unread_notifications_count': Notification.get_unread_count(current_user.id)}
        return {'unread_notifications_count': 0}

    from app.routes import main
    app.register_blueprint(main)

    from app.auth import auth
    app.register_blueprint(auth)

    return app