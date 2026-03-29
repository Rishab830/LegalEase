from flask_login import UserMixin
from flask import current_app
from bson import ObjectId
import bcrypt
from datetime import datetime


def get_mongo_db():
    """Get MongoDB instance from current app context."""
    return current_app.config.get('mongo_db')


class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password_hash')
        self.display_name = user_data.get('display_name', '')
        self.role = user_data.get('role', 'user')
        self.created_at = user_data.get('created_at')

    @staticmethod
    def get(user_id):
        mongo_db = get_mongo_db()
        user_data = mongo_db.users.find_one({'_id': ObjectId(user_id)})
        return User(user_data) if user_data else None

    @staticmethod
    def find_by_email(email):
        mongo_db = get_mongo_db()
        return mongo_db.users.find_one({'email': email})

    @staticmethod
    def find_by_username(username):
        mongo_db = get_mongo_db()
        return mongo_db.users.find_one({'username': username})

    @staticmethod
    def create_user(username, email, password, role='user'):
        mongo_db = get_mongo_db()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user_doc = {
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'role': role,
            'created_at': datetime.utcnow()
        }
        result = mongo_db.users.insert_one(user_doc)
        return str(result.inserted_id)

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    @staticmethod
    def update_profile(user_id, display_name=None, email=None):
        """Update user profile (display_name and/or email)."""
        mongo_db = get_mongo_db()
        update_data = {}
        
        if display_name is not None:
            update_data['display_name'] = display_name
        if email is not None:
            update_data['email'] = email
        
        if update_data:
            mongo_db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': update_data}
            )
            return True
        return False

    @staticmethod
    def update_password(user_id, new_password):
        """Update user password."""
        mongo_db = get_mongo_db()
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        mongo_db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'password_hash': password_hash}}
        )
        return True


class Notification:
    def __init__(self, n_data):
        self.id = str(n_data['_id'])
        self.user_id = n_data.get('user_id')
        self.type = n_data.get('type', 'info') # info, success, warning, danger
        self.message = n_data.get('message')
        self.link = n_data.get('link')
        self.is_read = n_data.get('is_read', False)
        self.created_at = n_data.get('created_at', datetime.utcnow())

    @staticmethod
    def create(user_id, n_type, message, link=None):
        mongo_db = get_mongo_db()
        n_doc = {
            'user_id': user_id,
            'type': n_type,
            'message': message,
            'link': link,
            'is_read': False,
            'created_at': datetime.utcnow()
        }
        result = mongo_db.notifications.insert_one(n_doc)
        return str(result.inserted_id)

    @staticmethod
    def get_unread_count(user_id):
        mongo_db = get_mongo_db()
        return mongo_db.notifications.count_documents({'user_id': user_id, 'is_read': False})

    @staticmethod
    def get_for_user(user_id, limit=20):
        mongo_db = get_mongo_db()
        notifications = list(mongo_db.notifications.find({'user_id': user_id}).sort('created_at', -1).limit(limit))
        return [Notification(n) for n in notifications]

    @staticmethod
    def mark_as_read(notification_id):
        mongo_db = get_mongo_db()
        mongo_db.notifications.update_one({'_id': ObjectId(notification_id)}, {'$set': {'is_read': True}})

    @staticmethod
    def mark_all_as_read(user_id):
        mongo_db = get_mongo_db()
        mongo_db.notifications.update_many({'user_id': user_id}, {'$set': {'is_read': True}})