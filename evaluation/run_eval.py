import json
import os
import evaluate
import time
from dotenv import load_dotenv

# Optional: if you want to use the existing Gemini client from the app
# from app.utils.gemini_client import get_gemini_client 

# Load environment variables (API keys)
load_dotenv()

# Load metrics
rouge = evaluate.load('rouge')
bertscore = evaluate.load('bertscore')

def get_llm_prediction(text, model_type="gemini"):
    """
    Placeholder for calling your LLM. 
    You should implement the actual API calls here.
    """
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

    if model_type == "gemini":
        # Example using Google Generative AI
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"short_summary": "Error: GEMINI_API_KEY not found."}
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # or 'gemini-1.5-pro'
        
        try:
            response = model.generate_content(prompt)
            # Basic JSON extraction (assuming the model returns valid JSON)
            content = response.text.strip()
            # Clean up markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:-3].strip()
            return json.loads(content)
        except Exception as e:
            print(f"Gemini Error: {e}")
            return {"short_summary": ""}

    elif model_type == "openai":
        # Example using OpenAI
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"OpenAI Error: {e}")
            return {"short_summary": ""}

    return {"short_summary": "Unknown model type."}

def run_evaluation(benchmark_file="evaluation/benchmark_ground_truth.json", model_to_test="gemini"):
    if not os.path.exists(benchmark_file):
        print(f"Error: {benchmark_file} not found. Run benchmark.py first.")
        return

    with open(benchmark_file, "r") as f:
        data = json.load(f)

    predictions = []
    ground_truths = []

    print(f"Evaluating {model_to_test} on {len(data)} samples...")

    for i, item in enumerate(data):
        print(f"Processing sample {i+1}/{len(data)}...")
        doc_text = item["document_text"]
        gt_summary = item["expected_output"]["short_summary"]
        
        # Get LLM prediction
        prediction_json = get_llm_prediction(doc_text, model_type=model_to_test)
        pred_summary = prediction_json.get("short_summary", "")

        predictions.append(pred_summary)
        ground_truths.append(gt_summary)
        
        # Avoid rate limits
        time.sleep(2)

    # Calculate ROUGE
    rouge_results = rouge.compute(predictions=predictions, references=ground_truths)
    
    # Calculate BERTScore
    bert_results = bertscore.compute(predictions=predictions, references=ground_truths, lang="en")
    avg_bert_f1 = sum(bert_results['f1']) / len(bert_results['f1'])

    print("\n--- Evaluation Results ---")
    print(f"Model: {model_to_test}")
    print(f"ROUGE-L: {rouge_results['rougeL']:.4f}")
    print(f"BERTScore (F1): {avg_bert_f1:.4f}")
    print("---------------------------\n")

if __name__ == "__main__":
    # To run this, you need GEMINI_API_KEY or OPENAI_API_KEY in your .env file
    run_evaluation(model_to_test="gemini")
