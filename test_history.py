import os
import pytest
from pymongo import MongoClient
from app import create_app
from app.models import User
from datetime import datetime
from uuid import uuid4

@pytest.fixture
def app():
    """Create app for testing with isolated test database."""
    # Isolated DB for history tests
    test_db_name = 'legalease_test_history_db'
    os.environ['MONGO_URI'] = f'mongodb://localhost:27017/{test_db_name}'
    
    # Use a separate uploads folder for testing to avoid touching production data
    test_upload_folder = os.path.join(os.getcwd(), 'tests', 'test_uploads')
    os.makedirs(test_upload_folder, exist_ok=True)
    
    cleanup_client = MongoClient('mongodb://localhost:27017/')
    try:
        cleanup_client.drop_database(test_db_name)
    except:
        pass
    cleanup_client.close()
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['UPLOAD_FOLDER'] = test_upload_folder
    
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
    # Cleanup after all tests in this fixture
    try:
        cleanup_client = MongoClient('mongodb://localhost:27017/')
        cleanup_client.drop_database(test_db_name)
        cleanup_client.close()
        
        # Optional: remove test uploads folder
        import shutil
        if os.path.exists(test_upload_folder):
            shutil.rmtree(test_upload_folder)
    except:
        pass
    
    ctx.pop()

@pytest.fixture
def client(app):
    return app.test_client()

def register_and_login(client, username, email, password):
    client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'confirm_password': password
    })
    client.post('/login', data={
        'email': email,
        'password': password
    })
    return User.find_by_email(email)

def create_mock_doc(app, user_id, filename, status='processed', doc_type='NDA'):
    mongo_db = app.config.get('mongo_db')
    doc_id = str(uuid4())
    stored_filename = f"{doc_id}.pdf"
    
    # Create dummy file in uploads
    upload_folder = app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    with open(os.path.join(upload_folder, stored_filename), 'w') as f:
        f.write('dummy content')
        
    doc = {
        'doc_id': doc_id,
        'user_id': str(user_id),
        'original_filename': filename,
        'stored_filename': stored_filename,
        'file_type': 'application/pdf',
        'upload_date': datetime.utcnow(),
        'status': status,
        'doc_type': doc_type
    }
    mongo_db.documents.insert_one(doc)
    return doc_id

class TestDocumentHistory:
    def test_user_sees_only_own_documents(self, app, client):
        # User A
        user_a = register_and_login(client, 'userA', 'a@example.com', 'password123')
        create_mock_doc(app, user_a['_id'], 'docA1.pdf')
        create_mock_doc(app, user_a['_id'], 'docA2.pdf')
        
        # User B
        client.get('/logout')
        user_b = register_and_login(client, 'userB', 'b@example.com', 'password123')
        create_mock_doc(app, user_b['_id'], 'docB1.pdf')
        
        # Check User B's history
        response = client.get('/documents')
        assert response.status_code == 200
        assert b'docB1.pdf' in response.data
        assert b'docA1.pdf' not in response.data
        assert b'docA2.pdf' not in response.data
        
        # Check User A's history
        client.get('/logout')
        register_and_login(client, 'userA', 'a@example.com', 'password123')
        response = client.get('/documents')
        assert response.status_code == 200
        assert b'docA1.pdf' in response.data
        assert b'docA2.pdf' in response.data
        assert b'docB1.pdf' not in response.data

    def test_delete_document_success(self, app, client):
        user = register_and_login(client, 'userD', 'd@example.com', 'password123')
        doc_id = create_mock_doc(app, user['_id'], 'delete_me.pdf')
        
        mongo_db = app.config.get('mongo_db')
        doc = mongo_db.documents.find_one({'doc_id': doc_id})
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc['stored_filename'])
        assert os.path.exists(file_path)
        
        # Delete
        response = client.post(f'/documents/{doc_id}/delete')
        assert response.status_code == 200
        assert response.json['success'] is True
        
        # Verify DB and File
        assert mongo_db.documents.find_one({'doc_id': doc_id}) is None
        assert not os.path.exists(file_path)

    def test_delete_document_unauthorized(self, app, client):
        # User A owns a doc
        user_a = register_and_login(client, 'userA', 'a@example.com', 'password123')
        doc_id = create_mock_doc(app, user_a['_id'], 'owner_A.pdf')
        
        # User B tries to delete User A's doc
        client.get('/logout')
        register_and_login(client, 'userB', 'b@example.com', 'password123')
        
        response = client.post(f'/documents/{doc_id}/delete')
        assert response.status_code == 403
        assert response.json['success'] is False
        assert response.json['message'] == 'Permission denied.'

    def test_re_analyze_document_success(self, app, client):
        user = register_and_login(client, 'userR', 'r@example.com', 'password123')
        doc_id = create_mock_doc(app, user['_id'], 'reanalyze.pdf', status='processed')
        
        response = client.post(f'/documents/{doc_id}/re-analyze')
        assert response.status_code == 200
        assert response.json['success'] is True
        
        mongo_db = app.config.get('mongo_db')
        doc = mongo_db.documents.find_one({'doc_id': doc_id})
        assert doc['status'] == 'uploaded'
        assert 're_analyzed_at' in doc

    def test_re_analyze_document_unauthorized(self, app, client):
        # User A owns a doc
        user_a = register_and_login(client, 'userA', 'a@example.com', 'password123')
        doc_id = create_mock_doc(app, user_a['_id'], 'owner_A_2.pdf')
        
        # User B tries to re-analyze User A's doc
        client.get('/logout')
        register_and_login(client, 'userB', 'b@example.com', 'password123')
        
        response = client.post(f'/documents/{doc_id}/re-analyze')
        assert response.status_code == 403
        assert response.json['success'] is False
        assert response.json['message'] == 'Permission denied.'
