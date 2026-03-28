# LegalEase

LegalEase is a Flask + MongoDB web application for legal document analysis. It is designed to let users upload legal documents, extract text, organize document records, and gradually evolve into a full clause analysis platform.

## Project Overview

The project is based on a backlog for a **Legal Document Clause Analyzer**. The current implementation focus starts with the Sprint 1 foundation: project setup, authentication, document upload, OCR, text cleaning, metadata storage, and document history.

## Planned Features

### Sprint 1
- User registration and login
- Profile management
- Upload legal documents in PDF, PNG, and JPG formats
- OCR for image-based documents
- Text cleaning and document type detection
- Store extracted text and metadata in MongoDB
- View, re-open, re-analyze, and delete uploaded documents

### Sprint 2
- Plain-English legal document summarization
- Structured summaries by section
- Clause extraction
- Risk flagging with Low/Medium/High labels
- Risk summary card
- Manual annotations and overrides for legal professionals
- Export document analysis

### Sprint 3
- Chat with a document using a RAG pipeline
- Source-grounded answers with document snippets
- Multi-document comparison
- In-app and email notifications
- Admin dashboard, analytics, and AI output review

## Tech Stack

- **Backend:** Flask
- **Database:** MongoDB with PyMongo
- **Authentication:** Flask-Login
- **OCR:** Tesseract via pytesseract
- **PDF Processing:** pdfplumber
- **Configuration:** python-dotenv
- **Deployment:** Render or Docker-based deployment

## Current Project Structure

```text
LegalEase/
│
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── templates/
│   │   └── home.html
│   └── static/
│       └── css/
│           └── style.css
│
├── uploads/
├── config.py
├── run.py
├── requirements.txt
├── .env
└── .gitignore
```

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd LegalEase
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

On Windows:

```bash
venv\Scriptsctivate
```

On Linux/macOS:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

```env
SECRET_KEY=your-secret-key
MONGO_URI=mongodb://localhost:27017/legalease_db
UPLOAD_FOLDER=uploads
```

### 5. Run the application

```bash
python run.py
```

Then open:

```text
http://127.0.0.1:5000/
```

## Configuration

The app uses environment-based settings from `config.py`:

- `SECRET_KEY` for Flask sessions and security
- `MONGO_URI` for MongoDB connection
- `UPLOAD_FOLDER` for uploaded files

## Health Check

A `/health` route is recommended to confirm that:

- the Flask app is running
- MongoDB is reachable
- the upload folder exists
- Tesseract is available on the server

## Deployment

For simple hosting, the app can be deployed on Render with MongoDB Atlas.

For OCR-based production deployment, Docker is recommended so that the Tesseract system package is installed reliably.

Typical production additions:

- `gunicorn` in `requirements.txt`
- a `Procfile` or `Dockerfile`
- environment variables configured on the hosting platform
- MongoDB Atlas connection string

## Testing

Recommended testing layers:

- unit tests for config and app creation
- route tests for authentication and uploads
- OCR tests for image edge cases
- PDF extraction tests
- integration tests for MongoDB-backed flows
- browser tests for full user journeys

## Roadmap

1. Set up Flask app factory and MongoDB connection
2. Add registration and login
3. Add profile management
4. Add document upload and storage
5. Add OCR and text extraction
6. Add document history and re-analysis
7. Add AI summarization and clause extraction
8. Add risk analysis
9. Add RAG chat
10. Add comparison, notifications, and admin analytics

## Notes

- `pytesseract` requires the **Tesseract OCR binary** to be installed on the machine.
- Local file storage is acceptable for early development, but cloud object storage is better for production.
- MongoDB records should store document metadata and extracted content linked to authenticated users.

## Contributors

Project managers listed in the backlog: **Ayush** and **Rishab**.

## License

Add your preferred license here.
