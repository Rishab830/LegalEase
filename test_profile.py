import os
import io
import json
import pytest
from pymongo import MongoClient
from app import create_app
from app.models import User


@pytest.fixture
def app():
    """Create app for testing with isolated test database."""
    # Set test config
    os.environ['MONGO_URI'] = 'mongodb://localhost:27017/legalease_test_db'
    
    # Clean up any leftover test database
    cleanup_client = MongoClient('mongodb://localhost:27017/')
    try:
        cleanup_client.drop_database('legalease_test_db')
    except:
        pass
    cleanup_client.close()
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Push app context and keep it active for the entire test
    ctx = app.app_context()
    ctx.push()
    
    # Drop users collection to start fresh
    mongo_db = app.config.get('mongo_db')
    try:
        mongo_db['users'].drop()
    except:
        pass
    
    yield app
    
    # Cleanup after test
    try:
        mongo_db['users'].drop()
    except:
        pass
    
    # Pop the app context
    ctx.pop()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create test client with authenticated user."""
    # Register and login a user
    client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    return client


class TestProfileAccess:
    """Test profile page access."""
    
    def test_profile_requires_authentication(self, client):
        """Test that accessing /profile without login redirects to login."""
        response = client.get('/profile', follow_redirects=False)
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_authenticated_user_can_access_profile(self, authenticated_client):
        """Test that authenticated user can access profile page and prefill user data."""
        response = authenticated_client.get('/profile')
        
        assert response.status_code == 200
        assert b'Profile Settings' in response.data
        assert b'Account Information' in response.data
        assert b'value="testuser"' in response.data
        assert b'value="test@example.com"' in response.data


class TestUpload:
    """Test document upload workflow."""

    def test_upload_requires_login(self, client):
        response = client.get('/upload', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.location

    def test_upload_pdf_success(self, authenticated_client, app):
        file_bytes = io.BytesIO(b'%PDF-1.4 sample')
        data = {
            'document': (file_bytes, 'test-document.pdf')
        }
        response = authenticated_client.post('/upload', data=data, content_type='multipart/form-data')

        assert response.status_code == 201
        result = json.loads(response.data)
        assert result['success'] is True
        assert 'doc_id' in result

        doc = app.config['mongo_db'].documents.find_one({'doc_id': result['doc_id']})
        assert doc is not None
        assert doc['original_filename'] == 'test-document.pdf'
        assert doc['stored_filename'].endswith('.pdf')
        app_user = User.find_by_email('test@example.com')
        assert app_user is not None
        assert doc['user_id'] == str(app_user['_id'])
        assert doc['status'] == 'uploaded'

        # Confirm file exists on disk
        uploaded_path = os.path.join(app.config['UPLOAD_FOLDER'], doc['stored_filename'])
        assert os.path.exists(uploaded_path)

    def test_upload_png_success(self, authenticated_client, app):
        file_bytes = io.BytesIO(b'\x89PNG\r\n\x1a\nPNG sample')
        data = {
            'document': (file_bytes, 'test-image.png')
        }
        response = authenticated_client.post('/upload', data=data, content_type='multipart/form-data')

        assert response.status_code == 201
        result = json.loads(response.data)
        assert result['success'] is True
        assert 'doc_id' in result

        doc = app.config['mongo_db'].documents.find_one({'doc_id': result['doc_id']})
        assert doc is not None
        assert doc['original_filename'] == 'test-image.png'
        assert doc['stored_filename'].endswith('.png')
        app_user = User.find_by_email('test@example.com')
        assert app_user is not None
        assert doc['user_id'] == str(app_user['_id'])
        assert doc['status'] == 'uploaded'

        uploaded_path = os.path.join(app.config['UPLOAD_FOLDER'], doc['stored_filename'])
        assert os.path.exists(uploaded_path)

    def test_upload_txt_or_exe_disallowed(self, authenticated_client, app):
        for filename in ['evil.exe', 'text.txt']:
            file_bytes = io.BytesIO(b'dummy content')
            data = {'document': (file_bytes, filename)}
            response = authenticated_client.post('/upload', data=data, content_type='multipart/form-data')

            assert response.status_code == 400
            result = json.loads(response.data)
            assert result['success'] is False
            assert 'Only PDF, PNG, and JPG files are allowed' in result['message']

        # ensure no documents were created
        docs = list(app.config['mongo_db'].documents.find({}))
        assert len(docs) == 0

    def test_upload_zero_byte_file_rejected(self, authenticated_client):
        file_bytes = io.BytesIO(b'')
        data = {'document': (file_bytes, 'empty.pdf')}
        response = authenticated_client.post('/upload', data=data, content_type='multipart/form-data')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'empty' in result['message'].lower()

    def test_upload_same_original_name_generates_unique_stored_filenames(self, authenticated_client, app):
        first = io.BytesIO(b'%PDF-1.4 first')
        second = io.BytesIO(b'%PDF-1.4 second')
        data1 = {'document': (first, 'same-name.pdf')}
        data2 = {'document': (second, 'same-name.pdf')}

        r1 = authenticated_client.post('/upload', data=data1, content_type='multipart/form-data')
        r2 = authenticated_client.post('/upload', data=data2, content_type='multipart/form-data')

        assert r1.status_code == 201
        assert r2.status_code == 201

        id1 = json.loads(r1.data)['doc_id']
        id2 = json.loads(r2.data)['doc_id']
        assert id1 != id2

        doc1 = app.config['mongo_db'].documents.find_one({'doc_id': id1})
        doc2 = app.config['mongo_db'].documents.find_one({'doc_id': id2})

        assert doc1 is not None
        assert doc2 is not None
        assert doc1['stored_filename'] != doc2['stored_filename']
        assert doc1['stored_filename'].endswith('.pdf')
        assert doc2['stored_filename'].endswith('.pdf')

        path1 = os.path.join(app.config['UPLOAD_FOLDER'], doc1['stored_filename'])
        path2 = os.path.join(app.config['UPLOAD_FOLDER'], doc2['stored_filename'])
        assert os.path.exists(path1)
        assert os.path.exists(path2)

    def test_upload_disallowed_extension(self, authenticated_client):
        file_bytes = io.BytesIO(b'dummy content')
        data = {
            'document': (file_bytes, 'evil.exe')
        }
        response = authenticated_client.post('/upload', data=data, content_type='multipart/form-data')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'Only PDF, PNG, and JPG files are allowed' in result['message']


class TestProfileUpdate:
    """Test profile update functionality."""
    
    def test_update_display_name_successfully(self, authenticated_client):
        """Test updating display name successfully."""
        response = authenticated_client.patch('/profile', 
            json={
                'display_name': 'Test User Display',
                'email': 'test@example.com',
                'current_password': None,
                'new_password': None,
                'confirm_password': None
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'successfully' in data['message'].lower()
        assert 'profile updated successfully' in data['message'].lower()
        
        # Verify update in database
        user = User.find_by_email('test@example.com')
        assert user['display_name'] == 'Test User Display'
    
    def test_update_email_successfully(self, authenticated_client):
        """Test updating email successfully."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'newemail@example.com',
                'current_password': None,
                'new_password': None,
                'confirm_password': None
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        
        # Verify update in database
        user = User.find_by_email('newemail@example.com')
        assert user is not None
        assert user['email'] == 'newemail@example.com'
    
    def test_update_rejects_duplicate_email(self, authenticated_client):
        """Test that duplicate email is rejected."""
        # Create another user
        authenticated_client.get('/logout')
        authenticated_client.post('/register', data={
            'username': 'user2',
            'email': 'user2@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Login original user and try to update to second user's email
        authenticated_client.get('/logout')
        authenticated_client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'user2@example.com',
                'current_password': None,
                'new_password': None,
                'confirm_password': None
            },
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Email already registered' in data['message']

        # Ensure original user email is unchanged after duplicate email attempt
        original_user = User.find_by_email('test@example.com')
        assert original_user is not None
        assert original_user['email'] == 'test@example.com'


class TestPasswordUpdate:
    """Test password update functionality."""
    
    def test_password_update_requires_current_password(self, authenticated_client):
        """Test that password update requires current password."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': None,
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Current password required' in data['message']
    
    def test_password_update_requires_correct_current_password(self, authenticated_client):
        """Test that password update requires correct current password."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': 'wrongpassword',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Current password is incorrect' in data['message']
    
    def test_password_update_requires_password_confirmation(self, authenticated_client):
        """Test that new passwords must match."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': 'password123',
                'new_password': 'newpassword123',
                'confirm_password': 'differentpassword'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'do not match' in data['message']
    
    def test_password_update_requires_minimum_length(self, authenticated_client):
        """Test that new password must be at least 6 characters."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': 'password123',
                'new_password': 'short',
                'confirm_password': 'short'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'at least 6 characters' in data['message']
    
    def test_password_update_successfully(self, authenticated_client):
        """Test successfully updating password."""
        # Get user's current password hash before change
        user_before = User.find_by_email('test@example.com')
        assert user_before is not None
        old_hash = user_before['password_hash']

        response = authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': 'password123',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'profile updated successfully' in data['message'].lower()

        # Re-fetch user after update
        user_after = User.find_by_email('test@example.com')
        assert user_after is not None
        assert user_after['password_hash'] != old_hash
        assert user_after['password_hash'] != 'newpassword123'

        updated_user = User(user_after)
        assert updated_user.check_password('newpassword123')
        assert not updated_user.check_password('password123')

        # Verify login with new password works
        authenticated_client.get('/logout')
        response = authenticated_client.post('/login', data={
            'email': 'test@example.com',
            'password': 'newpassword123'
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert '/dashboard' in response.location
    
    def test_old_password_no_longer_works_after_change(self, authenticated_client):
        """Test that old password doesn't work after change."""
        # Change password
        authenticated_client.patch('/profile',
            json={
                'display_name': None,
                'email': 'test@example.com',
                'current_password': 'password123',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            },
            content_type='application/json'
        )
        
        # Logout
        authenticated_client.get('/logout')
        
        # Try to login with old password
        response = authenticated_client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Invalid email or password' in response.data


class TestProfileCombinedUpdates:
    """Test updating multiple profile fields at once."""
    
    def test_update_display_name_and_email_together(self, authenticated_client):
        """Test updating display name and email in one request."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': 'My Display Name',
                'email': 'newemail@example.com',
                'current_password': None,
                'new_password': None,
                'confirm_password': None
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        
        # Verify both updates in database
        user = User.find_by_email('newemail@example.com')
        assert user['display_name'] == 'My Display Name'
        assert user['email'] == 'newemail@example.com'
    
    def test_update_all_fields_together(self, authenticated_client):
        """Test updating display name, email, and password in one request."""
        response = authenticated_client.patch('/profile',
            json={
                'display_name': 'Updated Display Name',
                'email': 'updatedemail@example.com',
                'current_password': 'password123',
                'new_password': 'newpassword456',
                'confirm_password': 'newpassword456'
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        
        # Verify updates in database
        user = User.find_by_email('updatedemail@example.com')
        assert user['display_name'] == 'Updated Display Name'
        
        # Verify new password works
        authenticated_client.get('/logout')
        response = authenticated_client.post('/login', data={
            'email': 'updatedemail@example.com',
            'password': 'newpassword456'
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert '/dashboard' in response.location
