import os
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.models import User

@pytest.fixture
def app():
    """Setup app for summarization testing with isolated DB."""
    test_db_name = 'legalease_test_summary_db'
    mongo_uri = f'mongodb://localhost:27017/{test_db_name}'
    
    # Force environment variable for Config class (in case it's not imported yet)
    os.environ['MONGO_URI'] = mongo_uri
    
    app = create_app()
    # Explicitly override config to be sure, then re-initialize mongo if create_app already ran with old config
    app.config['MONGO_URI'] = mongo_uri
    
    from pymongo import MongoClient
    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    # Ensure a fresh start
    client.drop_database(test_db_name)
    app.config['mongo_db'] = db
    
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['GEMINI_API_KEY'] = 'fake-testing-key'
    
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
    # Cleanup
    try:
        client.drop_database(test_db_name)
        client.close()
    except:
        pass
    ctx.pop()

@pytest.fixture
def client(app):
    return app.test_client()

def register_and_login(client):
    client.post('/register', data={
        'username': 'summaryuser',
        'email': 'summary@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'summary@example.com', 'password': 'password123'})
    return User.find_by_email('summary@example.com')

class TestSummarization:
    """Test summarization route, caching, and LLM integration."""
    
    @patch('google.generativeai.GenerativeModel.generate_content')
    def test_short_summary_generation_and_caching(self, mock_gen, client, app):
        """Verify short summary logic, sentence count, and MongoDB caching."""
        user = register_and_login(client)
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'test-summary-id'
        mongo_db.documents.insert_one({
            'doc_id': doc_id,
            'user_id': str(user['_id']),
            'status': 'processed',
            'cleaned_text': 'This is a sample legal text for testing the summarization feature.'
        })
        
        # 1. Mock first call (API hit)
        mock_response = MagicMock()
        mock_response.text = "This is sentence one. This is sentence two. This is sentence three. This is sentence four."
        mock_gen.return_value = mock_response
        
        response = client.get(f'/document/{doc_id}/summary?mode=short')
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert data['cache_hit'] is False
        assert "This is sentence one" in data['summary']
        
        # Verify sentence count (3-5 sentences heuristic)
        sentence_count = data['summary'].count('.')
        assert 3 <= sentence_count <= 5
        
        # 2. Verify Caching (second call should not trigger API)
        response_cached = client.get(f'/document/{doc_id}/summary?mode=short')
        assert response_cached.status_code == 200
        assert response_cached.json['cache_hit'] is True
        assert response_cached.json['summary'] == data['summary']
        
        # Ensure only one API call was made
        assert mock_gen.call_count == 1

    @patch('google.generativeai.GenerativeModel.generate_content')
    def test_detailed_summary_parsing(self, mock_gen, client, app):
        """Verify detailed summary returns correct JSON keys."""
        user = register_and_login(client)
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'test-detailed-id'
        mongo_db.documents.insert_one({
            'doc_id': doc_id,
            'user_id': str(user['_id']),
            'status': 'processed',
            'cleaned_text': 'Detailed contract text.'
        })
        
        # Mock JSON response (with markdown often added by LLMs)
        mock_response = MagicMock()
        mock_response.text = '```json\n{"Purpose": "Test Purpose", "Parties": "Test Parties", "Obligations": "Test Obligations", "Duration": "1 Year", "Termination": "30 days"}\n```'
        mock_gen.return_value = mock_response
        
        response = client.get(f'/document/<doc_id>/summary?mode=detailed'.replace('<doc_id>', doc_id))
        assert response.status_code == 200
        summary = response.json['summary']
        
        assert summary['Purpose'] == "Test Purpose"
        assert all(k in summary for k in ["Purpose", "Parties", "Obligations", "Duration", "Termination"])

    def test_summary_forbidden_for_other_user(self, client, app):
        """Verify user cannot access someone else's document summary."""
        # 1. Register User A and create a doc
        mongo_db = app.config.get('mongo_db')
        user_a_id = User.create_user('userA', 'a@example.com', 'password123')
        doc_id = 'doc-user-a'
        mongo_db.documents.insert_one({
            'doc_id': doc_id, 'user_id': str(user_a_id), 'status': 'processed'
        })
        
        # 2. Login as User B (different user)
        client.post('/register', data={
            'username': 'userB', 'email': 'b@example.com', 'password': 'password123', 'confirm_password': 'password123'
        })
        client.post('/login', data={'email': 'b@example.com', 'password': 'password123'})
        
        # 3. Access User A's doc - should be 403, NOT a redirect
        response = client.get(f'/document/{doc_id}/summary')
        assert response.status_code == 403

    def test_summary_conflict_for_unprocessed_doc(self, client, app):
        """Verify 409 Conflict if document status is not 'processed'."""
        user = register_and_login(client)
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'doc-uploaded'
        mongo_db.documents.insert_one({
            'doc_id': doc_id, 'user_id': str(user['_id']), 'status': 'uploaded'
        })
        
        response = client.get(f'/document/{doc_id}/summary')
        assert response.status_code == 409
        assert "not yet processed" in response.json['message']
