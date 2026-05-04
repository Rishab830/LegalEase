from app.utils.gemini_client import get_gemini_client
import numpy as np
import re
import time
from flask import current_app

def chunk_text(text, chunk_size=1000, overlap=150):
    """
    Split legal text into overlapping segments for RAG processing.
    Yields chunks as a generator to save RAM.
    """
    if not text:
        return
    if len(text) < chunk_size:
        yield text
        return
    
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Don't split words - look for a space near the end
        if end < len(text):
            # Look for a space in the last 25% of the chunk to keep chunks substantial
            search_start = max(start, end - (chunk_size // 4))
            last_space = text.rfind(' ', search_start, end)
            if last_space != -1:
                end = last_space
        
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
            
        # Ensure progress to avoid infinite loops
        next_start = end - overlap
        if next_start <= start:
            next_start = start + (chunk_size // 2) # Force progress
            
        start = next_start
        
        # Guard against hanging loops or reaching the end
        if start >= len(text) or (len(text) - start) < 50:
            # Yield remaining text if it's significant
            remaining = text[start:].strip()
            if remaining:
                yield remaining
            break

def get_embedding(text, task_type="retrieval_document"):
    """
    Generate 768-dimensional embedding vector(s) via Google Gemini API.
    Supports both a single string and a list of strings (batch processing).
    Includes retries for rate limiting.
    """
    client = get_gemini_client()
    if not client:
        return None
        
    import random
    retries = 5
    delay = 5.0
    
    for attempt in range(retries):
        try:
            # Using gemini-embedding-001 (was text-embedding-004 which 404s)
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={"task_type": task_type}
            )
            
            # If text was a string, return a single list of values
            if isinstance(text, str):
                if hasattr(response, 'embeddings') and len(response.embeddings) > 0:
                    return response.embeddings[0].values
            # If text was a list, return a list of lists of values
            else:
                if hasattr(response, 'embeddings'):
                    return [e.values for e in response.embeddings]
            return None
            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < retries - 1:
                    wait_time = delay + random.uniform(0, 2)
                    current_app.logger.warning(f"Rate limit hit for embedding. Retrying in {wait_time:.1f} seconds (Attempt {attempt+1}/{retries})...")
                    time.sleep(wait_time)
                    delay *= 2.5
                    continue
            current_app.logger.error(f"Gemini Embedding failed: {str(e)}")
            return None
    return None

def batch_list(iterable, batch_size=40):
    """
    Yield successive n-sized chunks from an iterable (list or generator).
    Prevents RAM overload by processing data in smaller batches.
    """
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch

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
    Uses a cursor to iterate over chunks to prevent RAM overload.
    """
    query_vector = get_embedding(query, task_type="retrieval_query")
    if not query_vector:
        return []
        
    mongo_db = current_app.config.get('mongo_db')
    # Use cursor to iterate instead of fetching all into a list at once
    doc_chunks_cursor = mongo_db.chunks.find({'doc_id': doc_id})
    
    results = []
    for chunk in doc_chunks_cursor:
        score = cosine_similarity(query_vector, chunk['embedding'])
        results.append({
            'text': chunk['text'],
            'score': score
        })
        
    # Sort by relevance score (descending)
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]
