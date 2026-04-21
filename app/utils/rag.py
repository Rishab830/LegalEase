from google import genai
import numpy as np
import re
from flask import current_app

def chunk_text(text, chunk_size=1000, overlap=150):
    """
    Split legal text into overlapping segments for RAG processing.
    Ensures context is preserved by having overlapping regions between chunks.
    """
    if not text or len(text) < 100:
        return [text] if text else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Don't split words - look for a space near the end
        if end < len(text):
            last_space = text.rfind(' ', start + (chunk_size // 2), end)
            if last_space != -1:
                end = last_space
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        start = end - overlap
        
        # Guard against hanging loops
        if start >= len(text) or (end - start) < 50:
            break
            
    return chunks

def get_embedding(text, task_type="retrieval_document"):
    """
    Generate a 768-dimensional embedding vector via Google Gemini API.
    """
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        # Using text-embedding-004
        result = client.models.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type=task_type
        )
        return result.embedding
    except Exception as e:
        current_app.logger.error(f"Gemini Embedding failed: {str(e)}")
        return None

def cosine_similarity(v1, v2):
    """Compute cosine similarity score (0-1) between two vectors."""
    try:
        vec1 = np.array(v1)
        vec2 = np.array(v2)
        dot_product = np.dot(vec1, vec2)
        norm_a = np.linalg.norm(vec1)
        norm_b = np.linalg.norm(vec2)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(dot_product / (norm_a * norm_b))
    except Exception as e:
        current_app.logger.error(f"Similarity calculation failed: {str(e)}")
        return 0.0

def get_relevant_chunks(doc_id, query, top_k=3):
    """
    Retrieves the most semantically relevant text segments for a query.
    """
    query_vector = get_embedding(query, task_type="retrieval_query")
    if not query_vector:
        return []
        
    mongo_db = current_app.config.get('mongo_db')
    # Fetch all chunks for this specific document
    doc_chunks = list(mongo_db.chunks.find({'doc_id': doc_id}))
    
    if not doc_chunks:
        return []
        
    results = []
    for chunk in doc_chunks:
        score = cosine_similarity(query_vector, chunk['embedding'])
        results.append({
            'text': chunk['text'],
            'score': score
        })
        
    # Sort by relevance score (descending)
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]
