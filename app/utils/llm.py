import google.generativeai as genai
import json
import re
from flask import current_app

def generate_summary(text, mode='short'):
    """
    Generate a legal document summary using Google Gemini AI.
    
    Modes:
    - 'short': Returns a string (3-5 sentences).
    - 'detailed': Returns a JSON object with sections: Purpose, Parties, Obligations, Duration, Termination.
    """
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        current_app.logger.error("GEMINI_API_KEY is not configured in the application.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        # Using gemini-1.5-flash for cost/speed efficiency in testing
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        if mode == 'short':
            prompt = (
                "You are an expert legal assistant. Summarize the following legal document in exactly 3 to 5 sentences. "
                "Highlight the core intent and significant legal context. Use professional language.\n\n"
                f"DOCUMENT TEXT:\n{text}"
            )
        else:
            prompt = (
                "You are an expert legal assistant. Analyze the following legal document and extract exactly these sections: "
                "Purpose, Parties, Obligations, Duration, and Termination. "
                "Your response MUST be a valid JSON object with these exact keys. "
                "If a section is not found in the text, use 'Not specified'. "
                "Return ONLY the raw JSON object, no introductory or concluding text.\n\n"
                f"DOCUMENT TEXT:\n{text}"
            )
            
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            current_app.logger.error("Empty response received from Gemini API.")
            return None
            
        content = response.text.strip()
        
        if mode == 'detailed':
            # Remove any markdown code block formatting (```json ... ```)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            try:
                parsed_json = json.loads(content)
                # Ensure all required keys are present
                required_keys = ["Purpose", "Parties", "Obligations", "Duration", "Termination"]
                for key in required_keys:
                    if key not in parsed_json:
                        parsed_json[key] = "Not specified"
                return parsed_json
            except json.JSONDecodeError as je:
                current_app.logger.error(f"Failed to parse LLM JSON response: {str(je)} | Content: {content}")
                return None
                
        return content
        
    except Exception as e:
        current_app.logger.error(f"Gemini API invocation failed: {str(e)}")
        return None


def analyze_clauses(text):
    """
    Identify critical legal clauses and their associated risk levels using Gemini AI.
    
    Returns:
        list: A list of dicts with keys ['name', 'risk_level', 'reasoning'].
    """
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        return None
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            "Analyze the following legal document and identify 3 to 5 critical legal clauses that require attention. "
            "For each clause, provide: 'name', 'risk_level' (High, Medium, or Low), and a concise 'reasoning'. "
            "Your response MUST be a valid JSON list of objects. "
            "Return ONLY the raw JSON list, no preamble or extra text.\n\n"
            f"DOCUMENT TEXT:\n{text}"
        )
        
        response = model.generate_content(prompt)
        if not response or not response.text:
            return None
            
        content = response.text.strip()
        
        # Clean potential markdown from response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
            
        try:
            clauses = json.loads(content)
            # Basic validation
            if isinstance(clauses, list):
                return clauses
            return None
        except json.JSONDecodeError as je:
            current_app.logger.error(f"Failed to parse clauses JSON: {str(je)} | Content: {content}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Gemini clause analysis failed: {str(e)}")
        return None


def compare_documents(text_a, text_b):
    """
    Compare two legal documents and generate a match score, key differences, and risk delta using Gemini AI.
    
    Returns:
        dict: A dict with keys ['match_score', 'key_differences', 'risk_delta'].
    """
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        return None
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            "You are a legal auditor comparing two versions/excerpts of a document: 'Document A' and 'Document B'. "
            "Compare them for semantic differences in intent, obligations, and risk. "
            "Provide your analysis as a valid JSON object with: "
            "1. 'match_score' (int 0-100), "
            "2. 'key_differences' (list of strings using '+' for additions/strengthening and '-' for removals/weakening in B), "
            "3. 'risk_delta' (concise summary of B's risk versus A). "
            "Return ONLY the raw JSON object.\n\n"
            f"DOCUMENT A:\n{text_a}\n\n"
            f"DOCUMENT B:\n{text_b}"
        )
        
        response = model.generate_content(prompt)
        if not response or not response.text:
            return None
            
        content = response.text.strip()
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
            
        try:
            comparison = json.loads(content)
            # Basic validation
            if isinstance(comparison, dict) and 'match_score' in comparison:
                return comparison
            return None
        except json.JSONDecodeError as je:
            current_app.logger.error(f"Failed to parse comparison JSON: {str(je)} | Content: {content}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Gemini document comparison failed: {str(e)}")
        return None
