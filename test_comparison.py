import os
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.models import User
from datetime import datetime

@pytest.fixture
def app():
    """Setup app for comparison testing with isolated DB."""
    test_db_name = 'legalease_test_compare_db'
    mongo_uri = f'mongodb://localhost:27017/{test_db_name}'
    os.environ['MONGO_URI'] = mongo_uri
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['GEMINI_API_KEY'] = 'fake-key'
    
    from pymongo import MongoClient
    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    client.drop_database(test_db_name)
    app.config['mongo_db'] = db
    
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
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
        'username': 'compareuser',
        'email': 'comp@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'comp@example.com', 'password': 'password123'})
    return User.find_by_email('comp@example.com')

class TestComparisonView:
    """Test document selection, type constraints, and AI comparison rendering."""
    
    @patch('app.utils.llm.compare_documents')
    def test_successful_side_by_side_comparison(self, mock_compare, client, app):
        """Verify two compatible documents can be compared successfully."""
        user = register_and_login(client)
        user_id = str(user['_id'])
        mongo_db = app.config.get('mongo_db')
        
        # Create 2 NDAs (compatible types)
        now = datetime.now()
        doc_a = {
            'doc_id': 'doc-a', 'user_id': user_id, 'status': 'processed', 
            'doc_type': 'NDA', 'original_filename': 'NDA_V1.pdf', 'upload_date': now,
            'cleaned_text': 'NDA Version 1 Content.'
        }
        doc_b = {
            'doc_id': 'doc-b', 'user_id': user_id, 'status': 'processed', 
            'doc_type': 'NDA', 'original_filename': 'NDA_V2.pdf', 'upload_date': now,
            'cleaned_text': 'NDA Version 2 Content with more rules.'
        }
        mongo_db.documents.insert_many([doc_a, doc_b])
        
        # Mock AI results
        mock_compare.return_value = {
            'match_score': 75,
            'key_differences': ['+ Added Indemnity Clause', '- Removed Arbitration'],
            'risk_delta': 'The risk has shifted towards the provider due to the new indemnity.'
        }
        
        # Perform comparison
        response = client.post('/compare', data={'doc_a': 'doc-a', 'doc_b': 'doc-b'})
        assert response.status_code == 200
        html = response.data.decode()
        
        # Verify UI contents
        assert "Match Score" in html
        assert "75" in html
        assert "Added Indemnity" in html
        assert "+" in html
        assert "Removed Arbitration" in html
        assert "-" in html
        assert "risk has shifted" in html
        assert "NDA_V1.pdf" in html
        assert "NDA_V2.pdf" in html

    def test_mismatched_document_types_error(self, client, app):
        """Verify that comparing incompatible types (e.g. NDA vs Contract) triggers an error."""
        user = register_and_login(client)
        user_id = str(user['_id'])
        mongo_db = app.config.get('mongo_db')
        
        # Create an NDA and a Contract
        now = datetime.now()
        mongo_db.documents.insert_many([
            {'doc_id': 'd1', 'user_id': user_id, 'status': 'processed', 'doc_type': 'NDA', 'original_filename': 'N.pdf', 'upload_date': now},
            {'doc_id': 'd2', 'user_id': user_id, 'status': 'processed', 'doc_type': 'Contract', 'original_filename': 'C.pdf', 'upload_date': now}
        ])
        
        response = client.post('/compare', data={'doc_a': 'd1', 'doc_b': 'd2'})
        assert response.status_code == 200 # Should return to selection page
        assert "Cannot compare documents of different types" in response.data.decode()

    def test_compare_selection_rendering(self, client, app):
        """Verify the selection page loads all available processed documents."""
        user = register_and_login(client)
        user_id = str(user['_id'])
        mongo_db = app.config.get('mongo_db')
        
        mongo_db.documents.insert_one({
            'doc_id': 's1', 'user_id': user_id, 'status': 'processed', 
            'original_filename': 'Selectable_Doc.pdf', 'doc_type': 'NDA', 'upload_date': datetime.now()
        })
        
        response = client.get('/compare')
        assert response.status_code == 200
        assert "Selectable_Doc.pdf" in response.data.decode()
        assert "Choose baseline" in response.data.decode()
