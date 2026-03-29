import threading
from flask import current_app
from app.utils.processor import run_pipeline

def start_background_processing(doc_id, file_path, ext, user_id):
    """
    Spawns a background thread to run the document analysis pipeline.
    Ensures the Flask app context is available inside the thread.
    """
    # Get the actual Flask app object (not the proxy)
    app = current_app._get_current_object()
    
    def thread_wrapper(app, doc_id, file_path, ext, user_id):
        # Push the app context manually inside the thread
        with app.app_context():
            try:
                run_pipeline(doc_id, file_path, ext, user_id=user_id)
            except Exception as e:
                app.logger.error(f"Background processing failed for {doc_id}: {str(e)}")

    # Start the thread as a daemon so it doesn't block server shutdown
    process_thread = threading.Thread(
        target=thread_wrapper,
        args=(app, doc_id, file_path, ext, user_id),
        daemon=True
    )
    process_thread.start()
    return process_thread
