import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
from app import create_app
from app.models import User
from io import BytesIO

@pytest.fixture
def app():
    """Create app for testing with isolated test database."""
    test_db_name = 'legalease_test_ocr_db'
    os.environ['MONGO_URI'] = f'mongodb://localhost:27017/{test_db_name}'
    
    # Use a separate uploads folder for testing
    test_upload_folder = os.path.join(os.getcwd(), 'tests', 'test_ocr_uploads')
    os.makedirs(test_upload_folder, exist_ok=True)
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['UPLOAD_FOLDER'] = test_upload_folder
    
    ctx = app.app_context()
    ctx.push()
    
    yield app
    
    # Cleanup after all tests in this fixture
    try:
        import shutil
        if os.path.exists(test_upload_folder):
            shutil.rmtree(test_upload_folder)
        # Drop database after tests
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
        'username': 'ocruser',
        'email': 'ocr@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={
        'email': 'ocr@example.com',
        'password': 'password123'
    })

def create_mock_img(filename='test.png', dpi=(72, 72)):
    img = Image.new('RGB', (100, 100), color=(255, 255, 255))
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG', dpi=dpi)
    img_byte_arr.seek(0)
    return img_byte_arr

class TestOCR:
    @patch('pytesseract.image_to_string')
    def test_upload_png_triggers_ocr(self, mock_ocr, client, app):
        """Test that uploading a PNG triggers OCR and updates status."""
        register_and_login(client)
        mock_ocr.return_value = "Extracted legal text content."
        
        img_data = create_mock_img('test.png')
        response = client.post('/upload', data={
            'document': (img_data, 'test.png')
        }, content_type='multipart/form-data')
        
        assert response.status_code == 201
        doc_id = response.json['doc_id']
        
        mongo_db = app.config.get('mongo_db')
        doc = mongo_db.documents.find_one({'doc_id': doc_id})
        assert doc['status'] == 'ocr_complete'
        assert doc['raw_text'] == "Extracted legal text content."
        mock_ocr.assert_called_once()

    @patch('pytesseract.image_to_string')
    @patch('PIL.Image.Image.resize')
    def test_low_res_upscaling(self, mock_resize, mock_ocr, client, app):
        """Test that low DPI triggers image upscaling."""
        register_and_login(client)
        mock_ocr.return_value = "Text from low res image."
        # Create a mock image for the resize result to keep PIL happy
        mock_resize.return_value = Image.new('RGB', (300, 300))
        
        # 72 DPI is < 150, should trigger resize
        img_data = create_mock_img('lowres.png', dpi=(72, 72))
        client.post('/upload', data={
            'document': (img_data, 'lowres.png')
        }, content_type='multipart/form-data')
        
        # Verify resize was called due to low DPI
        mock_resize.assert_called()

    @patch('pytesseract.image_to_osd')
    @patch('pytesseract.image_to_string')
    def test_skew_correction(self, mock_ocr, mock_osd, client, app):
        """Test that orientation detection (OSD) is called."""
        register_and_login(client)
        mock_osd.return_value = "Orientation in degrees: 90\nRotate: 90\nOrientation confidence: 10\n"
        mock_ocr.return_value = "Text from skewed image."
        
        img_data = create_mock_img('skewed.png')
        client.post('/upload', data={
            'document': (img_data, 'skewed.png')
        }, content_type='multipart/form-data')
        
        mock_osd.assert_called()

    @patch('pytesseract.image_to_string')
    def test_blank_image_returns_ocr_empty(self, mock_ocr, client, app):
        """Test that blank images result in ocr_empty status."""
        register_and_login(client)
        mock_ocr.return_value = "   " # Effectively empty
        
        img_data = create_mock_img('blank.png')
        response = client.post('/upload', data={
            'document': (img_data, 'blank.png')
        }, content_type='multipart/form-data')
        
        doc_id = response.json['doc_id']
        mongo_db = app.config.get('mongo_db')
        doc = mongo_db.documents.find_one({'doc_id': doc_id})
        assert doc['status'] == 'ocr_empty'

    @patch('pytesseract.image_to_string')
    def test_pdf_does_not_trigger_ocr(self, mock_ocr, client, app):
        """Test that PDF uploads bypass the OCR path."""
        register_and_login(client)
        
        # Create a dummy PDF
        pdf_data = BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<Root 1 0 R>>\n%%EOF")
        client.post('/upload', data={
            'document': (pdf_data, 'test.pdf')
        }, content_type='multipart/form-data')
        
        mock_ocr.assert_not_called()
