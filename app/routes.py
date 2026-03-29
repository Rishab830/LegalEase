import os
from uuid import uuid4
from datetime import datetime

from flask import Blueprint, render_template, current_app, jsonify, request, send_from_directory, redirect, url_for, send_file
from flask_login import login_required, current_user
from app.models import Notification
from app.utils.ocr import perform_ocr
from app.utils.processor import extract_pdf_text, clean_text, classify_document, run_pipeline
from app.utils.background_processor import start_background_processing

main = Blueprint("main", __name__)





@main.route("/")
# ... (rest of the file)


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

        # Trigger Extraction & Cleaning Pipeline in the background
        start_background_processing(doc_id, file_path, ext, user_id=current_user.id)

        return jsonify({
            'success': True, 
            'message': 'Upload successful! Your document is being analyzed in the background.', 
            'doc_id': doc_id, 
            'filename': stored_filename, 
            'ext': ext
        }), 202
    except Exception as e:
        current_app.logger.error('Upload error: %s', e)
        return jsonify({'success': False, 'message': 'Upload failed.'}), 500

@main.route('/uploads/<filename>')
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
        # Determine extension and file path from stored filename
        ext = os.path.splitext(doc['stored_filename'])[1].lower().strip('.')
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc['stored_filename'])

        # Reset status and run pipeline in the background
        mongo_db.documents.update_one(
            {'doc_id': doc_id},
            {'$set': {'status': 're-processing', 're_analyzed_at': datetime.utcnow()}}
        )

        start_background_processing(doc_id, file_path, ext, user_id=current_user.id)

        return jsonify({'success': True, 'message': 'Re-analysis started in the background.'})
    except Exception as e:
        current_app.logger.error('Re-analyze error: %s', e)
        return jsonify({'success': False, 'message': 'Failed to trigger re-analysis.'}), 500


@main.route("/document/<doc_id>/summary")
@login_required
def get_summary(doc_id):
    """Retrieve or generate a summary of a document."""
    mode = request.args.get('mode', 'short')
    if mode not in ['short', 'detailed']:
        return jsonify({'success': False, 'message': 'Invalid mode (use "short" or "detailed").'}), 400

    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc:
        return jsonify({'success': False, 'message': 'Document not found.'}), 404

    if doc['user_id'] != current_user.id:
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    if doc.get('status') != 'processed':
        return jsonify({'success': False, 'message': 'Document not yet processed. Please wait or re-analyze.'}), 409

    # Check MongoDB cache
    summary_data = doc.get('summary', {})
    if mode in summary_data:
        return jsonify({
            'success': True,
            'summary': summary_data[mode],
            'cache_hit': True,
            'mode': mode
        })

    # Generate summary using LLM
    cleaned_text = doc.get('cleaned_text', '')
    if not cleaned_text:
        return jsonify({'success': False, 'message': 'No text found in document to summarize.'}), 400

    from app.utils.llm import generate_summary
    summary = generate_summary(cleaned_text, mode=mode)

    if summary:
        mongo_db.documents.update_one(
            {'doc_id': doc_id},
            {'$set': {f'summary.{mode}': summary}}
        )
        return jsonify({
            'success': True,
            'summary': summary,
            'cache_hit': False,
            'mode': mode
        })
    else:
        return jsonify({'success': False, 'message': 'Failed to generate summary via AI.'}), 500


@main.route("/document/<doc_id>/analysis")
@login_required
def get_analysis(doc_id):
    """Render the detailed analysis dashboard for a document."""
    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc:
        return "Document not found", 404
    if doc['user_id'] != current_user.id:
        return "Permission denied", 403
    # We allow the page to load even if status != 'processed'
    # The template will handle showing a placeholder if needed.

    # Lazy initialization for AI components (caching)
    # ONLY attempt this if processing is complete and text is available
    if doc.get('status') == 'processed' and 'cleaned_text' in doc:
        from app.utils.llm import generate_summary, analyze_clauses
        
        summary = doc.get('summary', {})
        updated = False
        
        if 'short' not in summary:
            res = generate_summary(doc['cleaned_text'], mode='short')
            if res:
                summary['short'] = res
                updated = True
                
        if 'detailed' not in summary:
            res = generate_summary(doc['cleaned_text'], mode='detailed')
            if res:
                summary['detailed'] = res
                updated = True
                
        if 'clauses' not in summary:
            res = analyze_clauses(doc['cleaned_text'])
            if res:
                summary['clauses'] = res
                updated = True

        if updated:
            mongo_db.documents.update_one({'doc_id': doc_id}, {'$set': {'summary': summary}})
    else:
        summary = doc.get('summary', {})

    return render_template("analysis.html", doc=doc, summary=summary)


@main.route("/document/<doc_id>/download")
@login_required
def download_document(doc_id):
    """Download the cleaned text of a document as a .txt file."""
    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc or doc['user_id'] != current_user.id:
        return "Unauthorized", 403

    from flask import Response
    content = doc.get('cleaned_text', 'No text extracted.')
    safe_filename = "".join([c for c in doc['original_filename'] if c.isalnum() or c in (' ', '.', '_')]).strip()
    filename = f"{os.path.splitext(safe_filename)[0]}_cleaned.txt"

    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@main.route("/compare", methods=['GET', 'POST'])
@login_required
def compare_documents_route():
    """Select and compare two documents side-by-side."""
    mongo_db = current_app.config.get('mongo_db')
    
    if request.method == 'GET':
        # Fetch all processed documents for the user to select from
        user_docs = list(mongo_db.documents.find({
            'user_id': current_user.id,
            'status': 'processed'
        }).sort('upload_date', -1))
        return render_template("compare_select.html", documents=user_docs)

    # POST logic: Receive two document IDs and perform AI comparison
    doc_a_id = request.form.get('doc_a')
    doc_b_id = request.form.get('doc_b')

    if not doc_a_id or not doc_b_id:
        return redirect(url_for('main.compare_documents_route'))

    if doc_a_id == doc_b_id:
        user_docs = list(mongo_db.documents.find({
            'user_id': current_user.id,
            'status': 'processed'
        }).sort('upload_date', -1))
        return render_template("compare_select.html", documents=user_docs, error="Please select two DIFFERENT documents to compare.")

    doc_a = mongo_db.documents.find_one({'doc_id': doc_a_id})
    doc_b = mongo_db.documents.find_one({'doc_id': doc_b_id})

    if not doc_a or not doc_b:
        return "Document(s) not found.", 404
        
    if doc_a['user_id'] != current_user.id or doc_b['user_id'] != current_user.id:
        return "Unauthorized access to these documents.", 403

    # Restriction: Must be of the same type for a valid comparison
    if doc_a.get('doc_type') != doc_b.get('doc_type'):
        user_docs = list(mongo_db.documents.find({
            'user_id': current_user.id,
            'status': 'processed'
        }).sort('upload_date', -1))
        return render_template("compare_select.html", documents=user_docs, error="Cannot compare documents of different types.")

    from app.utils.llm import compare_documents
    comparison = compare_documents(doc_a.get('cleaned_text', ''), doc_b.get('cleaned_text', ''))
    
    if not comparison:
        user_docs = list(mongo_db.documents.find({
            'user_id': current_user.id,
            'status': 'processed'
        }).sort('upload_date', -1))
        return render_template("compare_select.html", documents=user_docs, error="AI comparison engine timed out. Please try again.")

    return render_template("compare_result.html", doc_a=doc_a, doc_b=doc_b, comparison=comparison)


@main.route("/document/<doc_id>/chat", methods=['POST'])
@login_required
def chat_with_document(doc_id):
    """Handle RAG-based chat queries for a specific document."""
    data = request.get_json() or {}
    question = data.get('question')

    if not question:
        return jsonify({'success': False, 'message': 'Question is required.'}), 400

    mongo_db = current_app.config.get('mongo_db')
    doc = mongo_db.documents.find_one({'doc_id': doc_id})

    if not doc:
        return jsonify({'success': False, 'message': 'Document not found.'}), 404
    if doc['user_id'] != current_user.id:
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    from app.utils.rag import get_relevant_chunks
    import google.generativeai as genai

    # 1. Retrieval
    relevant_chunks = get_relevant_chunks(doc_id, question, top_k=3)
    context_text = "\n\n---\n\n".join([c['text'] for c in relevant_chunks])

    if not context_text:
        return jsonify({
            'success': True, 
            'answer': "I'm sorry, I couldn't find any relevant sections in this document to answer that question.",
            'sources': []
        })

    # 2. Augmentation & Generation
    system_prompt = (
        "You are 'LegalEase AI', an expert legal assistant. Your task is to answer questions about a legal document "
        "using ONLY the provided context snippets. If the information is not present in the snippets, "
        "honestly state that the document does not mention it. Do not use outside knowledge. "
        "Keep your response structured, professional, and clear.\n\n"
        f"DOCUMENT CONTEXT SNIPPETS:\n{context_text}\n\n"
        f"USER QUESTION: {question}"
    )

    try:
        api_key = current_app.config.get('GEMINI_API_KEY')
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        response = model.generate_content(system_prompt)
        
        if not response or not response.text:
            return jsonify({'success': False, 'message': 'AI failed to generate a response.'}), 500

        return jsonify({
            'success': True,
            'answer': response.text,
            'sources': [c['text'] for c in relevant_chunks]
        })
    except Exception as e:
        current_app.logger.error(f"Chat error: {str(e)}")
        return jsonify({'success': False, 'message': 'An internal error occurred during chat.'}), 500


# --- Notification Routes ---

@main.route("/notifications")
@login_required
def notifications():
    """Display user's notification list."""
    user_notifications = Notification.get_for_user(current_user.id, limit=50)
    return render_template("notifications.html", notifications=user_notifications)


@main.route("/api/notifications/mark-read/<notification_id>", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read."""
    Notification.mark_as_read(notification_id)
    return jsonify({'success': True})


@main.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user."""
    Notification.mark_all_as_read(current_user.id)
    return jsonify({'success': True})
