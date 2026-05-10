import re
import pdfplumber
import os
import time
from flask import current_app
from app.utils.ocr import perform_ocr
from app.utils.rag import chunk_text, get_embedding, batch_list
from app.utils.llm import generate_full_analysis
from app.utils.notifications import notify_processing_complete, notify_high_risk_detected

def extract_pdf_text(file_path):
    """
    Extract raw text from a PDF file using pdfplumber.
    Concatenates text from all pages.
    """
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                else:
                    current_app.logger.warning(f"Could not extract text from page {i+1} of {file_path}. Page might be an image.")
                    
        return text.strip()
    except Exception as e:
        current_app.logger.error(f"PDF extraction failed for {file_path}: {str(e)}")
        return ""

def clean_text(text):
    """
    Shared text-cleaning pipeline for both OCR and PDF extracts.
    Strips headers, footers, page numbers using regex, and normalizes whitespace.
    """
    if not text:
        return ""
    
    patterns = [
        r'^Page\s+\d+\s+of\s+\d+\s*$', 
        r'^\d+\s+/\s+\d+\s*$',           
        r'^Page\s+\d+\s*$',
        r'^\d+\s*$',
        r'^CONFIDENTIAL\s*$',
        r'^STRICTLY PRIVATE\s*$',
        r'^All rights reserved\s*$',
        r'^Copyright © \d{4}.*$'
    ]
    
    inline_patterns = [
        r'Page\s+\d+\s+of\s+\d+',
        r'Page\s+\d+',
        r'CONFIDENTIAL',
        r'STRICTLY PRIVATE',
        r'^\s*[:\-\s]+'
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        temp_line = line.strip()
        if not temp_line:
            continue
            
        is_pure_boilerplate = False
        for pattern in patterns:
            if re.match(pattern, temp_line, flags=re.IGNORECASE):
                is_pure_boilerplate = True
                break
        
        if not is_pure_boilerplate:
            for pattern in inline_patterns:
                temp_line = re.sub(pattern, '', temp_line, flags=re.IGNORECASE).strip()
            if temp_line:
                cleaned_lines.append(temp_line)
    
    joined_text = ' '.join(cleaned_lines)
    cleaned_text = re.sub(r'\s+', ' ', joined_text).strip()
    
    return cleaned_text

def classify_document(text):
    """
    Rule-based document type classifier based on keyword frequency.
    """
    if not text:
        return "Unknown"
        
    text_lower = text.lower()
    
    keywords = {
        'NDA': ['non-disclosure', 'confidentiality', 'confidential', 'disclosing party', 'receiving party', 'proprietary information', 'nondisclosure'],
        'Contract': ['agreement', 'hereby agree', 'parties', 'consideration', 'binding', 'force majeure', 'termination', 'indemnification', 'signing', 'contract'],
        'Terms & Conditions': ['terms of service', 'user agreement', 'by using this website', 'acceptable use', 'terms and conditions', 't&c', 'legal notice', 'disclaimer of warranties'],
        'Privacy Policy': ['privacy policy', 'personal data', 'cookies', 'gdpr', 'data collection', 'pii', 'data processing']
    }
    
    scores = {key: 0 for key in keywords.keys()}
    for doc_type, word_list in keywords.items():
        for word in word_list:
            scores[doc_type] += text_lower.count(word)
            
    if 'non-disclosure' in text_lower or 'nondisclosure' in text_lower:
        scores['NDA'] += 5

    best_type = max(scores, key=scores.get)
    if scores[best_type] >= 1:
        return best_type
        
    return "Unknown"

def run_pipeline(doc_id, file_path, ext, user_id=None):
    """
    Orchestrate the complete document processing pipeline.
    """
    mongo_db = current_app.config.get('mongo_db')
    raw_text = ""
    status = 'processing_failed'

    # 1. Extraction
    if ext in {'png', 'jpg', 'jpeg'}:
        raw_text, ocr_status = perform_ocr(file_path)
        if ocr_status == 'ocr_failed':
            status = 'ocr_failed'
    elif ext == 'pdf':
        raw_text = extract_pdf_text(file_path)

    # 2. Shared Processing
    if raw_text:
        cleaned_text = clean_text(raw_text)
        doc_type = classify_document(cleaned_text)

        # 3. RAG Vectorization (Batched to prevent RAM overload)
        # chunks is now a generator, batch_list handles it efficiently
        chunks_generator = chunk_text(cleaned_text)
        mongo_db.chunks.delete_many({'doc_id': doc_id})
        
        total_processed_chunks = 0
        for batch_index, text_batch in enumerate(batch_list(chunks_generator, batch_size=40)):
            # Stagger batch embedding calls slightly to prevent rate limiting
            if batch_index > 0:
                time.sleep(2)
                
            embeddings = get_embedding(text_batch)
            if embeddings:
                batch_docs = []
                for i, embedding in enumerate(embeddings):
                    batch_docs.append({
                        'doc_id': doc_id,
                        'chunk_index': (batch_index * 40) + i,
                        'text': text_batch[i],
                        'embedding': embedding
                    })
                if batch_docs:
                    mongo_db.chunks.insert_many(batch_docs)
                    total_processed_chunks += len(batch_docs)
        
        # 4. Full Analysis (Summary + Sections + Clauses)
        # Delay slightly before starting next LLM task to respect rate limits
        time.sleep(3)
        analysis = generate_full_analysis(cleaned_text)
        
        # Atomically update document status and metadata
        update_data = {
            'raw_text': raw_text,
            'cleaned_text': cleaned_text,
            'doc_type': doc_type,
            'status': 'processed',
            'chunk_count': total_processed_chunks
        }
        
        clauses = []
        if analysis:
            update_data['summary'] = {
                'short': analysis.get('short_summary'),
                'detailed': analysis.get('sections'),
                'clauses': analysis.get('clauses')
            }
            clauses = analysis.get('clauses', [])

        mongo_db.documents.update_one(
            {'doc_id': doc_id},
            {'$set': update_data}
        )
            
        # 5. Trigger Notifications
        if user_id:
            filename = ""
            doc_record = mongo_db.documents.find_one({'doc_id': doc_id})
            if doc_record:
                filename = doc_record.get('original_filename', 'Document')
            
            # Processing complete notification
            notify_processing_complete(user_id, doc_id, filename)
            
            # High risk alert
            if clauses:
                high_risk = [c for c in clauses if c.get('risk_level') == 'High']
                if high_risk:
                    notify_high_risk_detected(user_id, doc_id, filename, high_risk)
                    
        return True
    else:
        mongo_db.documents.update_one(
            {'doc_id': doc_id},
            {'$set': {'status': status}}
        )
        return False
