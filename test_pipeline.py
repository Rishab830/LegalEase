import os
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from app import create_app
from app.utils.processor import clean_text, classify_document

class TestPipelineLogic:
    """Test individual components of the text processor."""
    
    def test_cleaning_logic(self):
        """Verify headers, footers, and page numbers are stripped."""
        dirty_text = """Page 1 of 10
        This is the main legal content.
        Confidential Agreement
        STRICTLY PRIVATE
        Article 1: Definitions.
        1 / 2
        All rights reserved"""
        
        cleaned = clean_text(dirty_text)
        
        # Check stripping
        assert "Page 1 of 10" not in cleaned
        assert "Confidential" not in cleaned
        assert "STRICTLY PRIVATE" not in cleaned
        assert "1 / 2" not in cleaned
        assert "rights reserved" not in cleaned
        
        # Check preservation
        assert "Article 1" in cleaned
        assert "main legal content" in cleaned
        
        # Check normalization (no multiple spaces)
        assert "  " not in cleaned

    def test_classification_nda(self):
        """Verify identification of NDA documents."""
        text = "This is a Non-Disclosure Agreement. The disclosing party and receiving party agree to keep all proprietary information confidential."
        assert classify_document(text) == "NDA"

    def test_classification_privacy(self):
        """Verify identification of Privacy Policies."""
        text = "Privacy Policy. We collect personal data such as email and cookies in accordance with GDPR. This policy explains our data processing."
        assert classify_document(text) == "Privacy Policy"

    def test_classification_terms(self):
        """Verify identification of Terms & Conditions."""
        text = "Terms and Conditions. By using this website, you agree to our terms of service and acceptable use policy."
        assert classify_document(text) == "Terms & Conditions"

    def test_classification_contract(self):
        """Verify identification of generic Contracts."""
        text = "This binding Agreement is made between the parties for valuable consideration. It is a signed contract."
        assert classify_document(text) == "Contract"

    def test_classification_unknown(self):
        """Verify fallback for irrelevant text."""
        text = "The quick brown fox jumps over the lazy dog. Hello world."
        assert classify_document(text) == "Unknown"

@pytest.fixture
def app():
    """Setup app for end-to-end pipeline testing."""
    test_db_name = 'legalease_test_pipeline_db'
    os.environ['MONGO_URI'] = f'mongodb://localhost:27017/{test_db_name}'
    
    test_upload_folder = os.path.join(os.getcwd(), 'tests', 'test_pipeline_uploads')
    os.makedirs(test_upload_folder, exist_ok=True)
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['UPLOAD_FOLDER'] = test_upload_folder
    
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
    # Cleanup
    try:
        import shutil
        if os.path.exists(test_upload_folder):
            shutil.rmtree(test_upload_folder)
        from pymongo import MongoClient
        cleanup_client = MongoClient('mongodb://localhost:27017/')
        cleanup_client.drop_database(test_db_name)
        cleanup_client.close()
    except:
        pass
    ctx.pop()

@pytest.fixture
def client(app):
    return app.test_client()

def register_and_login(client):
    client.post('/register', data={
        'username': 'pipelineuser',
        'email': 'pipeline@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'pipeline@example.com', 'password': 'password123'})

class TestPipelineEndToEnd:
    """Test full upload and re-analyze flows with integrated pipeline."""
    
    @patch('pdfplumber.open')
    def test_upload_pdf_triggers_full_pipeline(self, mock_pdf_open, client, app):
        """Verify end-to-end PDF processing: Upload -> Extract -> Clean -> Classify -> DB."""
        register_and_login(client)
        
        # Mock multi-page PDF
        mock_pdf = MagicMock()
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1: Non-Disclosure agreement contents."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2: Confidential proprietary info."
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf
        
        pdf_data = BytesIO(b"%PDF-1.4 dummy contents")
        response = client.post('/upload', data={
            'document': (pdf_data, 'test_nda.pdf')
        }, content_type='multipart/form-data')
        
        assert response.status_code == 201
        doc_id = response.json['doc_id']
        
        mongo_db = app.config.get('mongo_db')
        doc = mongo_db.documents.find_one({'doc_id': doc_id})
        
        # Verify results
        assert doc['status'] == 'processed'
        assert doc['doc_type'] == 'NDA'
        assert "Non-Disclosure" in doc['raw_text']
        assert "proprietary info" in doc['raw_text']
        assert "Page 1" not in doc['cleaned_text'] # Cleaning check
        assert doc['cleaned_text'].startswith("Non-Disclosure")

    @patch('pdfplumber.open')
    def test_re_analyze_triggers_full_pipeline(self, mock_pdf_open, client, app):
        """Verify re-analyzing a document runs it through the pipeline again."""
        register_and_login(client)
        
        # 1. Create a document in DB that was "failed" or just "uploaded"
        mongo_db = app.config.get('mongo_db')
        user = mongo_db.users.find_one({'email': 'pipeline@example.com'})
        doc_id = 'test-reanalyze-id'
        stored_filename = f"{doc_id}.pdf"
        
        # Create dummy file on disk
        with open(os.path.join(app.config['UPLOAD_FOLDER'], stored_filename), 'w') as f:
            f.write("dummy")
            
        mongo_db.documents.insert_one({
            'doc_id': doc_id,
            'user_id': str(user['_id']),
            'stored_filename': stored_filename,
            'status': 'uploaded'
        })
        
        # 2. Mock processing
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Terms of Service. These terms constitute the user agreement for our site."
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf
        
        # 3. Trigger Re-analyze
        response = client.post(f'/documents/{doc_id}/re-analyze')
        assert response.status_code == 200
        
        # 4. Verify updated state
        updated_doc = mongo_db.documents.find_one({'doc_id': doc_id})
        assert updated_doc['status'] == 'processed'
        assert updated_doc['doc_type'] == 'Terms & Conditions'
        assert updated_doc['cleaned_text'] == "Terms of Service. These terms constitute the user agreement for our site."
