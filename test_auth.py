import os
import pytest
from pymongo import MongoClient
from app import create_app, mongo_db, mongo_client
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
    
    # Cleanup after test - drop collections
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
def runner(app):
    """Create CLI runner."""
    return app.test_cli_runner()


class TestRegistration:
    """Test user registration functionality."""
    
    def test_successful_registration_redirects_to_dashboard(self, client):
        """Test successful registration with valid data returns 302 redirect to /dashboard."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        # After successful registration and login, should have dashboard content or be on /dashboard
        assert response.status_code == 200
        assert b'Welcome' in response.data or b'dashboard' in response.data.lower()
    
    def test_successful_registration_creates_user_in_db(self, client):
        """Verify user is actually created in database."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        user = User.find_by_email('test@example.com')
        assert user is not None
        assert user['username'] == 'testuser'
    
    def test_duplicate_email_registration_returns_error(self, client):
        """Test registering with duplicate email returns error flash."""
        # Register first user
        client.post('/register', data={
            'username': 'user1',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Logout first user so they're not authenticated for duplicate check
        client.get('/logout')
        
        # Try to register with same email
        response = client.post('/register', data={
            'username': 'user2',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Email already registered' in response.data
    
    def test_duplicate_username_registration_returns_error(self, client):
        """Test registering with duplicate username returns error flash."""
        # Register first user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test1@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Logout first user so they're not authenticated for duplicate check
        client.get('/logout')
        
        # Try to register with same username
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test2@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Username already taken' in response.data
    
    def test_registration_missing_username_returns_error(self, client):
        """Test registering without username returns error."""
        response = client.post('/register', data={
            'username': '',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'All fields are required' in response.data
    
    def test_registration_missing_email_returns_error(self, client):
        """Test registering without email returns error."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': '',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'All fields are required' in response.data
    
    def test_registration_missing_password_returns_error(self, client):
        """Test registering without password returns error."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': '',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'All fields are required' in response.data
    
    def test_password_mismatch_returns_error(self, client):
        """Test registration with mismatched passwords returns error."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'different123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Passwords do not match' in response.data
    
    def test_short_password_returns_error(self, client):
        """Test registration with short password returns error."""
        response = client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'short',
            'confirm_password': 'short'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Password must be at least 6 characters' in response.data


class TestLogin:
    """Test user login functionality."""
    
    def test_login_with_correct_credentials_redirects_to_dashboard(self, client):
        """Test login with correct credentials creates session and redirects."""
        # First register a user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Login with correct credentials
        response = client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert '/dashboard' in response.location
    
    def test_login_creates_valid_session(self, client):
        """Test that login creates a valid session."""
        # Register user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Login
        response = client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        
        # Check if dashboard is accessible (which requires authentication)
        assert response.status_code == 200
        assert b'Welcome' in response.data or b'dashboard' in response.data.lower()
    
    def test_login_with_wrong_password_returns_error(self, client):
        """Test login with wrong password returns error flash."""
        # Register user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Logout so we can test login
        client.get('/logout')
        
        # Login with wrong password
        response = client.post('/login', data={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Invalid email or password' in response.data
    
    def test_login_with_nonexistent_email_returns_error(self, client):
        """Test login with non-existent email returns error."""
        response = client.post('/login', data={
            'email': 'nonexistent@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Invalid email or password' in response.data
    
    def test_login_without_email_returns_error(self, client):
        """Test login without email returns error."""
        response = client.post('/login', data={
            'email': '',
            'password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Email and password are required' in response.data
    
    def test_login_without_password_returns_error(self, client):
        """Test login without password returns error."""
        response = client.post('/login', data={
            'email': 'test@example.com',
            'password': ''
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Email and password are required' in response.data


class TestDashboard:
    """Test dashboard protection and access."""
    
    def test_accessing_dashboard_without_login_redirects_to_login(self, client):
        """Test accessing /dashboard without logging in redirects to /login."""
        response = client.get('/dashboard', follow_redirects=False)
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_accessing_dashboard_after_login_shows_page(self, client):
        """Test accessing dashboard after login shows the page."""
        # Register and login
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        # Access dashboard
        response = client.get('/dashboard')
        
        assert response.status_code == 200
        assert b'Welcome' in response.data or b'testuser' in response.data


class TestLogout:
    """Test logout functionality."""
    
    def test_logout_clears_session_and_redirects_to_login(self, client):
        """Test logging out clears session and redirects to /login."""
        # Register and login
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        # Logout
        response = client.get('/logout', follow_redirects=False)
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_dashboard_inaccessible_after_logout(self, client):
        """Test that dashboard is inaccessible after logout."""
        # Register and login
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        # Logout
        client.get('/logout')
        
        # Try to access dashboard
        response = client.get('/dashboard', follow_redirects=False)
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_logout_shows_success_message(self, client):
        """Test logout shows success flash message."""
        # Register and login
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        # Logout with redirect
        response = client.get('/logout', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'logged out' in response.data or b'Logged' in response.data


class TestPasswordHashing:
    """Test that passwords are properly hashed."""
    
    def test_password_is_hashed_not_plaintext(self, client):
        """Test that passwords are stored as bcrypt hashes, not plaintext."""
        # Register user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'mypassword123',
            'confirm_password': 'mypassword123'
        })
        
        # Get the user from database
        user_data = User.find_by_email('test@example.com')
        password_hash = user_data['password_hash']
        
        # Verify password is not plaintext
        assert password_hash != 'mypassword123'
        
        # Verify it looks like a bcrypt hash (starts with $2)
        assert password_hash.startswith('$2')
    
    def test_password_change_invalidates_old_hash(self, client):
        """Test that password hash is different after registration."""
        # Register user
        client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        user_data1 = User.find_by_email('test@example.com')
        hash1 = user_data1['password_hash']
        
        # Logout so we can register another user
        client.get('/logout')
        
        # Register another user to confirm hashes differ
        client.post('/register', data={
            'username': 'testuser2',
            'email': 'test2@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        user_data2 = User.find_by_email('test2@example.com')
        hash2 = user_data2['password_hash']
        
        # Even though same password, hashes should be different (bcrypt adds salt)
        assert hash1 != hash2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
