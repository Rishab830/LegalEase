import os
from uuid import uuid4
from datetime import datetime

from flask import Blueprint, render_template, current_app, jsonify, request, send_from_directory
from flask_login import login_required, current_user
from app.utils.ocr import perform_ocr

main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html", project_name="LegalEase")


@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


@main.route("/health")
def health():
    try:
        # Access mongo_client from app config
        mongo_db = current_app.config.get('mongo_db')
        if mongo_db:
            mongo_db.client.admin.command("ping")
            db_status = "connected"
        else:
            db_status = "not configured"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        "app": "LegalEase",
        "status": "running",
        "database": db_status,
        "upload_folder": current_app.config["UPLOAD_FOLDER"]
    })


@main.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Upload document endpoint (UI form + file upload).

    Accepts only PDF, PNG, JPG/JPEG
    Saves file in uploads/ with UUID filename.
    Creates MongoDB document entry in documents collection.
    """
    if request.method == 'GET':
        return render_template('upload.html')

    # POST process file upload
    if 'document' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in request.'}), 400

    uploaded_file = request.files['document']

    if uploaded_file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected.'}), 400

    allowed_ext = {'pdf', 'png', 'jpg', 'jpeg'}
    filename = uploaded_file.filename
    content_type = uploaded_file.content_type or ''
    ext = os.path.splitext(filename)[1].lower().strip('.')

    if ext not in allowed_ext:
        return jsonify({'success': False, 'message': 'Only PDF, PNG, and JPG files are allowed.'}), 400

    # Reject empty uploads
    try:
        uploaded_file.stream.seek(0, os.SEEK_END)
        file_size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0)
    except Exception:
        file_size = None

    if file_size == 0:
        return jsonify({'success': False, 'message': 'Uploaded file is empty.'}), 400

    # Strict content-type check, this is defensive not authoritative
    allowed_types = {
        'pdf': 'application/pdf',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg'
    }

    expected_type = allowed_types.get(ext)
    if expected_type and content_type != expected_type:
        return jsonify({'success': False, 'message': 'Invalid file type.'}), 400

    doc_id = str(uuid4())
    stored_filename = f"{doc_id}.{ext}"
    upload_folder = current_app.config['UPLOAD_FOLDER']
    file_path = os.path.join(upload_folder, stored_filename)

    try:
        uploaded_file.save(file_path)

        mongo_db = current_app.config.get('mongo_db')
        document = {
            'doc_id': doc_id,
            'user_id': current_user.id,
            'original_filename': filename,
            'stored_filename': stored_filename,
            'file_type': content_type,
            'upload_date': datetime.utcnow(),
            'status': 'uploaded'
        }

        mongo_db.documents.insert_one(document)

        # Trigger OCR for image uploads
        if ext in {'png', 'jpg', 'jpeg'}:
            raw_text, ocr_status = perform_ocr(file_path)
            mongo_db.documents.update_one(
                {'doc_id': doc_id},
                {'$set': {'raw_text': raw_text, 'status': ocr_status}}
            )

        return jsonify({'success': True, 'doc_id': doc_id, 'filename': stored_filename, 'ext': ext}), 201
    except Exception as e:
        current_app.logger.error('Upload error: %s', e)
        return jsonify({'success': False, 'message': 'Upload failed.'}), 500

@main.route('/uploads/<filename>')
@login_required
def get_uploaded_file(filename):
    """Serve the uploaded files."""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@main.route("/documents")
@login_required
def documents():
    """Display user's document history."""
    mongo_db = current_app.config.get('mongo_db')
    user_docs = list(mongo_db.documents.find({'user_id': current_user.id}).sort('upload_date', -1))
    return render_template("documents.html", documents=user_docs)


@main.route("/documents/<doc_id>/delete", methods=["POST"])
@login_required
def delete_document(doc_id):
    """Delete a document record and its file."""
    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc:
        return jsonify({'success': False, 'message': 'Document not found.'}), 404

    if doc['user_id'] != current_user.id:
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    try:
        # Delete file from disk
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc['stored_filename'])
        if os.path.exists(file_path):
            os.remove(file_path)

        # Delete record from MongoDB
        mongo_db.documents.delete_one({'doc_id': doc_id})

        return jsonify({'success': True, 'message': 'Document deleted successfully.'})
    except Exception as e:
        current_app.logger.error('Delete error: %s', e)
        return jsonify({'success': False, 'message': 'Failed to delete document.'}), 500


@main.route("/documents/<doc_id>/re-analyze", methods=["POST"])
@login_required
def re_analyze_document(doc_id):
    """Reset document status to trigger re-analysis."""
    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc:
        return jsonify({'success': False, 'message': 'Document not found.'}), 404

    if doc['user_id'] != current_user.id:
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    try:
        mongo_db.documents.update_one(
            {'doc_id': doc_id},
            {'$set': {'status': 'uploaded', 're_analyzed_at': datetime.utcnow()}}
        )
        return jsonify({'success': True, 'message': 'Re-analysis triggered successfully.'})
    except Exception as e:
        current_app.logger.error('Re-analyze error: %s', e)
        return jsonify({'success': False, 'message': 'Failed to trigger re-analysis.'}), 500
