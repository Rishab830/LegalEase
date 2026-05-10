from app.utils.gemini_client import get_gemini_client
import json
import re
import time
import random
from flask import current_app

def generate_full_analysis(text):
    """
    Perform a complete document analysis in a SINGLE Gemini API call.
    Returns:
        dict: {
            'short_summary': str,
            'detailed_sections': dict,
            'clauses': list
        }
    """
    client = get_gemini_client()
    if not client:
        return None
        
    retries = 5
    delay = 10.0 # Higher initial delay for consolidated call
    
    prompt = (
        "You are an expert legal auditor. Analyze the provided legal document and provide a comprehensive analysis. "
        "Your response MUST be a valid JSON object with the following structure:\n\n"
        "{\n"
        "  'short_summary': 'A 3-5 sentence professional overview of the document intent.',\n"
        "  'sections': {\n"
        "     'Purpose': '...', 'Parties': '...', 'Obligations': '...', 'Duration': '...', 'Termination': '...'\n"
        "  },\n"
        "  'clauses': [\n"
        "     {'name': 'Clause Name', 'risk_level': 'High/Medium/Low', 'reasoning': '...'},\n"
        "     ... (identify 3-5 critical clauses)\n"
        "  ]\n"
        "}\n\n"
        f"DOCUMENT TEXT:\n{text}"
    )

    for attempt in range(retries):
        try:
            model_id = 'gemini-2.5-flash'
            current_app.logger.debug(f"Gemini Full Analysis Prompt: {prompt[:500]}...")
            
            response = client.models.generate_content(
                model=model_id, 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            
            if not response or not response.text:
                current_app.logger.error("Empty response received from Gemini API.")
                return None
                
            content = response.text.strip()
            current_app.logger.debug(f"Gemini Full Analysis Response: {content[:500]}...")
            
            analysis = json.loads(content)
            # Normalization/Safety checks
            if 'short_summary' not in analysis: analysis['short_summary'] = "Summary unavailable."
            if 'sections' not in analysis: analysis['sections'] = {}
            if 'clauses' not in analysis: analysis['clauses'] = []
            
            return analysis
            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < retries - 1:
                    wait_time = delay + random.uniform(0, 5)
                    current_app.logger.warning(f"Rate limit hit for Full Analysis. Retrying in {wait_time:.1f}s (Attempt {attempt+1}/{retries})...")
                    time.sleep(wait_time)
                    delay *= 2
                    continue
            current_app.logger.error(f"Gemini Full Analysis failed: {str(e)}")
            return None
    return None

def generate_summary(text, mode='short'):
    """
    Generate a summary of the text. 
    Uses generate_full_analysis to get data and returns either the short summary 
    or the structured sections depending on the mode.
    """
    analysis = generate_full_analysis(text)
    if not analysis:
        return None
        
    if mode == 'short':
        return analysis.get('short_summary')
    else:
        # For 'detailed' mode, return the sections dict
        return analysis.get('sections')

def analyze_clauses(text):
    """
    Identify critical legal clauses and their associated risk levels using Gemini AI.
    
    Returns:
        list: A list of dicts with keys ['name', 'risk_level', 'reasoning'].
    """
    client = get_gemini_client()
    if not client:
        return None
        
    retries = 5
    delay = 5.0
    
    for attempt in range(retries):
        try:
            model_id = 'gemini-2.5-flash'
            
            prompt = (
                "Analyze the following legal document and identify 3 to 5 critical legal clauses that require attention. "
                "For each clause, provide: 'name', 'risk_level' (High, Medium, or Low), and a concise 'reasoning'. "
                "Your response MUST be a valid JSON list of objects.\n\n"
                f"DOCUMENT TEXT:\n{text}"
            )
            
            current_app.logger.debug(f"Gemini Clause Analysis Prompt: {prompt[:500]}...")
            response = client.models.generate_content(
                model=model_id, 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            if not response or not response.text:
                return None
                
            content = response.text.strip()
            current_app.logger.debug(f"Gemini Clause Analysis Response: {content[:500]}...")
                
            try:
                clauses = json.loads(content)
                if isinstance(clauses, list):
                    return clauses
                # If it returned an object with a key like 'clauses'
                if isinstance(clauses, dict):
                    for val in clauses.values():
                        if isinstance(val, list):
                            return val
                return None
            except json.JSONDecodeError as je:
                current_app.logger.error(f"Failed to parse clauses JSON: {str(je)} | Content: {content}")
                return None
                
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < retries - 1:
                    wait_time = delay + random.uniform(0, 2)
                    current_app.logger.warning(f"Rate limit hit for analyze_clauses. Retrying in {wait_time:.1f} seconds (Attempt {attempt+1}/{retries})...")
                    time.sleep(wait_time)
                    delay *= 2.5
                    continue
            current_app.logger.error(f"Gemini clause analysis failed: {str(e)}")
            return None
            
    return None

def compare_documents(text_a, text_b):
    """
    Compare two legal documents and generate a match score, key differences, and risk delta using Gemini AI.
    
    Returns:
        dict: A dict with keys ['match_score', 'key_differences', 'risk_delta'].
    """
    client = get_gemini_client()
    if not client:
        return None
        
    retries = 5
    delay = 5.0
    
    for attempt in range(retries):
        try:
            model_id = 'gemini-2.5-flash'
            
            prompt = (
                "You are a legal auditor comparing two versions/excerpts of a document: 'Document A' and 'Document B'. "
                "Compare them for semantic differences in intent, obligations, and risk. "
                "Provide your analysis as a valid JSON object with: "
                "1. 'match_score' (int 0-100), "
                "2. 'key_differences' (list of strings using '+' for additions/strengthening and '-' for removals/weakening in B), "
                "3. 'risk_delta' (concise summary of B's risk versus A).\n\n"
                f"DOCUMENT A:\n{text_a}\n\n"
                f"DOCUMENT B:\n{text_b}"
            )
            
            current_app.logger.debug(f"Gemini Comparison Prompt: {prompt[:500]}...")
            response = client.models.generate_content(
                model=model_id, 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            if not response or not response.text:
                return None
                
            content = response.text.strip()
            current_app.logger.debug(f"Gemini Comparison Response: {content[:500]}...")
                
            try:
                comparison = json.loads(content)
                if isinstance(comparison, dict) and 'match_score' in comparison:
                    return comparison
                return None
            except json.JSONDecodeError as je:
                current_app.logger.error(f"Failed to parse comparison JSON: {str(je)} | Content: {content}")
                return None
                
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < retries - 1:
                    wait_time = delay + random.uniform(0, 2)
                    current_app.logger.warning(f"Rate limit hit for compare_documents. Retrying in {wait_time:.1f} seconds (Attempt {attempt+1}/{retries})...")
                    time.sleep(wait_time)
                    delay *= 2.5
                    continue
            current_app.logger.error(f"Gemini document comparison failed: {str(e)}")
            return None
            
    return None
