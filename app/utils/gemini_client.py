import threading
from google import genai
from flask import current_app

_thread_local = threading.local()

def get_gemini_client():
    """
    Returns a thread-local instance of the Google Gemini client.
    Caches the client after first initialization to prevent resource leaks
    caused by creating many client instances in short succession.
    """
    if not hasattr(_thread_local, 'client'):
        api_key = current_app.config.get('GEMINI_API_KEY')
        if not api_key:
            return None
        try:
            # We instantiate the client once per thread.
            _thread_local.client = genai.Client(api_key=api_key)
        except Exception as e:
            current_app.logger.error(f"Failed to initialize Gemini Client: {str(e)}")
            return None
            
    return _thread_local.client
