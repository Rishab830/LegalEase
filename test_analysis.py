import os
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.models import User
from datetime import datetime

@pytest.fixture
def app():
    """Setup app for analysis testing with isolated DB."""
    test_db_name = 'legalease_test_analysis_db'
    mongo_uri = f'mongodb://localhost:27017/{test_db_name}'
    os.environ['MONGO_URI'] = mongo_uri
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['GEMINI_API_KEY'] = 'fake-testing-key'
    
    from pymongo import MongoClient
    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    client.drop_database(test_db_name)
    app.config['mongo_db'] = db
    
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
    """Utility to register and login a user for testing."""
    client.post('/register', data={
        'username': 'analysisuser',
        'email': 'analysis@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'analysis@example.com', 'password': 'password123'})
    return User.find_by_email('analysis@example.com')

class TestAnalysisDashboard:
    """Test analysis page rendering, AI component orchestration, and downloads."""
    
    @patch('app.utils.llm.generate_summary')
    @patch('app.utils.llm.analyze_clauses')
    def test_analysis_page_rendering_and_logic(self, mock_clauses, mock_summary, client, app):
        """Verify the analysis page renders components and triggers AI if missing."""
        user_data = register_and_login(client)
        user_id = str(user_data['_id'])
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'test-analysis-001'
        mongo_db.documents.insert_one({
            'doc_id': doc_id,
            'user_id': user_id,
            'status': 'processed',
            'original_filename': 'NDA_Legal.pdf',
            'stored_filename': 'nda.pdf',
            'cleaned_text': 'This is the body of the NDA.',
            'doc_type': 'NDA',
            'upload_date': datetime.now(),
            'summary': {} # Empty summary to trigger generation
        })
        
        # Mock AI responses
        # First call: short summary, Second call: detailed summary
        mock_summary.side_effect = [
            "This is a mocked short 3-sentence summary.",
            {"Purpose": "Testing Analysis", "Parties": "User/AI", "Obligations": "Maintain Code", "Duration": "Indefinite", "Termination": "At will"}
        ]
        # Mock clauses
        mock_clauses.return_value = [
            {"name": "Liability Cap", "risk_level": "High", "reasoning": "Exposes company to high risk."},
            {"name": "Governing Law", "risk_level": "Low", "reasoning": "Standard jurisdiction."}
        ]
        
        # Access analysis page
        response = client.get(f'/document/{doc_id}/analysis')
        assert response.status_code == 200
        html = response.data.decode()
        
        # 1. Verify Components are present
        assert "NDA_Legal.pdf" in html
        assert "Short summary" in html.lower() or "summary" in html.lower()
        assert "This is a mocked short" in html
        
        # 2. Verify Structured Table
        assert "Obligations" in html
        assert "Maintain Code" in html
        assert "Termination" in html
        
        # 3. Verify Risk Analysis
        assert "High Risk" in html
        assert "Liability Cap" in html
        assert "Low Risk" in html
        assert "Governing Law" in html
        
        # 4. Verify AI triggers (should have been called because 'summary' was empty)
        assert mock_summary.call_count == 2
        assert mock_clauses.call_count == 1

    def test_download_cleaned_text(self, client, app):
        """Verify cleaned text download functionality."""
        user_data = register_and_login(client)
        user_id = str(user_data['_id'])
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'test-download-id'
        cleaned_body = "Line 1 of legal doc.\nLine 2 of legal doc."
        mongo_db.documents.insert_one({
            'doc_id': doc_id,
            'user_id': user_id,
            'status': 'processed',
            'original_filename': 'test_document.pdf',
            'cleaned_text': cleaned_body
        })
        
        response = client.get(f'/document/{doc_id}/download')
        assert response.status_code == 200
        
        # Verify Headers
        assert 'attachment' in response.headers['Content-Disposition']
        assert 'test_document_cleaned.txt' in response.headers['Content-Disposition']
        assert response.mimetype == 'text/plain'
        
        # Verify Content
        assert response.data.decode() == cleaned_body

    def test_analysis_unauthorized_access(self, client, app):
        """Verify a user cannot view another user's analysis dashboard."""
        mongo_db = app.config.get('mongo_db')
        
        # Create doc for User A
        user_a_id = User.create_user('userA', 'a@example.com', 'pass123')
        doc_id = 'doc-a'
        mongo_db.documents.insert_one({
            'doc_id': doc_id, 'user_id': user_a_id, 'status': 'processed'
        })
        
        # Login as User B
        client.post('/register', data={
            'username': 'userB', 'email': 'b@example.com', 'password': 'password123', 'confirm_password': 'password123'
        })
        client.post('/login', data={'email': 'b@example.com', 'password': 'password123'})
        
        response = client.get(f'/document/{doc_id}/analysis')
        assert response.status_code == 403
