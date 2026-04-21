import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app import create_app
from app.models import User
from app.utils.rag import chunk_text, cosine_similarity

@pytest.fixture
def app():
    """Setup app for RAG testing with isolated DB."""
    test_db_name = 'legalease_test_rag_db'
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
        'username': 'raguser',
        'email': 'rag@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'rag@example.com', 'password': 'password123'})
    return User.find_by_email('rag@example.com')

class TestRAGInterface:
    """Test chunking logic, similarity matching, and chat endpoints."""

    def test_text_chunking_and_overlap(self):
        """Verify that text is split into overlapping chunks correctly."""
        # Create a long string of words
        text = " ".join([f"word{i}" for i in range(500)]) # ~3000+ chars
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        
        assert len(chunks) > 1
        # Check for overlap: last part of chunk 0 should be in chunk 1
        last_part_of_first = chunks[0][-50:]
        assert last_part_of_first in chunks[1]

    def test_cosine_similarity_edge_cases(self):
        """Verify similarity calculation handles zero vectors and identical vectors."""
        v1 = [1, 0, 0]
        v2 = [1, 0, 0]
        v3 = [0, 1, 0]
        v_zero = [0, 0, 0]
        
        assert cosine_similarity(v1, v2) == pytest.approx(1.0)
        assert cosine_similarity(v1, v3) == pytest.approx(0.0)
        assert cosine_similarity(v1, v_zero) == 0.0

    @patch('app.utils.rag.get_embedding')
    @patch('google.genai.Client.models')
    def test_end_to_end_chat_endpoint(self, mock_gen, mock_embed, client, app):
        """Verify that the chat endpoint retrieves context and generates an answer."""
        user = register_and_login(client)
        user_id = str(user['_id'])
        mongo_db = app.config.get('mongo_db')
        
        doc_id = 'rag-test-doc'
        mongo_db.documents.insert_one({
            'doc_id': doc_id, 'user_id': user_id, 'status': 'processed',
            'original_filename': 'contract.pdf'
        })
        
        # Insert mock chunks with known vectors
        # Dummy 768-dim vector (normalized for direct dot product equivalence)
        vec_a = [0.1] * 768
        mongo_db.chunks.insert_one({
            'doc_id': doc_id, 
            'text': 'The termination notice period is 90 days.',
            'embedding': vec_a
        })
        
        # Mock Embedding for query
        mock_embed.return_value = vec_a
        
        # Mock AI Response
        mock_response = MagicMock()
        mock_response.text = "Based on the document, you need to provide a 90-day notice for termination."
        mock_gen.return_value = mock_response
        
        # POST Chat request
        response = client.post(f'/document/{doc_id}/chat', json={
            'question': 'How long is the termination notice?'
        })
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert "90-day notice" in data['answer']
        assert "termination notice period" in data['sources'][0]
        
        # Verify Mocks were called
        assert mock_embed.called
        assert mock_gen.called

    def test_chat_unauthorized_access(self, client, app):
        """Verify users cannot chat with documents they do not own."""
        mongo_db = app.config.get('mongo_db')
        user_a_id = User.create_user('userA', 'a@example.com', 'password123')
        doc_id = 'secret-doc'
        mongo_db.documents.insert_one({
            'doc_id': doc_id, 'user_id': user_a_id, 'status': 'processed'
        })
        
        # Login as User B
        client.post('/register', data={
            'username': 'userB', 'email': 'b@example.com', 'password': 'password123', 'confirm_password': 'password123'
        })
        client.post('/login', data={'email': 'b@example.com', 'password': 'password123'})
        
        response = client.post(f'/document/{doc_id}/chat', json={'question': 'Hello?'})
        assert response.status_code == 403
        assert response.json['success'] is False
