import json
import os
import time
import random
import evaluate
from google import genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Metrics
rouge = evaluate.load('rouge')
bertscore = evaluate.load('bertscore')
meteor = evaluate.load('meteor')

MODELS_TO_TEST = [
    "gemini-2.5-flash",
    "github:gpt-4o",   
    "github:gpt-4o-mini",
    "github:Meta-Llama-3.1-405B-Instruct",
    "github:Meta-Llama-3.1-8B-Instruct"   
]

def get_llm_prediction(text, model_name):
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

    
    retries = 10
    delay = 15.0

    for attempt in range(retries):
        try:
            content = None
            if model_name == "gemini" or model_name.startswith("gemini-"):
                api_key = os.getenv("GEMINI_API_KEY")
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name, 
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
                content = response.text.strip()

            elif model_name.startswith("github:"):
                gh_model = model_name[7:] 
                gh_token = os.getenv("GITHUB_TOKEN")
                client = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=gh_token)
                
                response = client.chat.completions.create(
                    model=gh_model,
                    messages=[
                        {"role": "system", "content": "You are a legal auditor. You must respond with a valid JSON object. Do not include any text before or after the JSON. Escape all newlines and double quotes within strings."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4096, 
                    **({"response_format": {"type": "json_object"}} if "gpt-4o" in gh_model.lower() else {})
                )
                content = response.choices[0].message.content.strip()
            
            if not content:
                raise Exception(f"Model {model_name} returned no content.")

            # --- Robust JSON Extraction & Cleaning ---
            import re
            
            # 1. Find the actual JSON block
            start = content.find('{')
            end = content.rfind('}')
            if start == -1 or end == -1:
                raise Exception("No JSON object found in the response.")
            
            clean_content = content[start:end+1]
            
            # 2. Fix common "small model" mistakes
            # Fix keys: 'name': -> "name":
            clean_content = re.sub(r"(?m)^\s*'(\w+)':", r'  "\1":', clean_content)
            clean_content = re.sub(r"([,{]\s*)'(\w+)':", r'\1"\2":', clean_content)
            
            # Fix string values: : 'Value' -> : "Value"
            clean_content = re.sub(r":\s*'([^']*)'(\s*[,}])", r': "\1"\2', clean_content)
            
            # 3. Handle unescaped newlines inside JSON strings (Most common failure)
            # This logic finds content between double quotes and escapes real newlines
            def escape_newlines(match):
                return match.group(0).replace('\n', '\\n').replace('\r', '\\r')
            
            clean_content = re.sub(r'":\s*"[^"]*"', escape_newlines, clean_content, flags=re.DOTALL)
            
            # 4. Remove trailing commas
            clean_content = re.sub(r',\s*([\]}])', r'\1', clean_content)

            try:
                analysis = json.loads(clean_content)
            except json.JSONDecodeError as e:
                # Last ditch effort: if it's still failing, it might be truncated. 
                # Try adding a closing bracket if it's missing.
                if not clean_content.endswith('}'):
                    try:
                        analysis = json.loads(clean_content + '}')
                    except:
                        raise e
                else:
                    raise e
            
            if 'short_summary' not in analysis: analysis['short_summary'] = "Summary unavailable."
            return analysis

        except Exception as e:
            err_msg = str(e)
            if any(x in err_msg for x in ["429", "RESOURCE_EXHAUSTED", "Rate limit"]):
                wait_time = delay + random.uniform(5, 15)
                print(f"  ⏳ Rate limit hit ({model_name}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                delay *= 1.2
                continue
            elif any(x in err_msg for x in ["503", "UNAVAILABLE", "overloaded"]):
                print(f"  🧱 Server overloaded. Waiting 30s...")
                time.sleep(30)
                continue
            
            print(f"  ❌ Error calling {model_name}: {err_msg}")
            return None
    return None

def main():
    benchmark_file = "evaluation/benchmark_ground_truth.json"
    with open(benchmark_file, "r") as f:
        data = json.load(f)

    test_data = data[:10]

    for model in MODELS_TO_TEST:
        print(f"\n🚀 EVALUATING FLAGSHIP: {model}")
        
        safe_name = model.replace('github:', '').replace('/', '_')
        results_file = f"evaluation/results_{safe_name}.json"
        
        existing_results = {"metrics": {}, "samples": []}
        if os.path.exists(results_file):
            try:
                with open(results_file, "r") as f:
                    existing_results = json.load(f)
            except: pass

        processed_ids = [s["id"] for s in existing_results["samples"]]
        predictions = [s["prediction"] for s in existing_results["samples"]]
        ground_truths = [s["ground_truth"] for s in existing_results["samples"]]

        for i, item in enumerate(test_data):
            if item["id"] in processed_ids:
                print(f"  ✅ [{i+1}/10] Skipping {item['id']}")
                continue
            
            print(f"  ➡️ [{i+1}/10] Processing {item['id']}...")
            prediction = get_llm_prediction(item['document_text'], model)
            
            if prediction and "short_summary" in prediction:
                pred_summary = prediction["short_summary"]
                gt_summary = item["expected_output"]["short_summary"]
                
                predictions.append(pred_summary)
                ground_truths.append(gt_summary)
                
                existing_results["samples"].append({
                    "id": item["id"],
                    "ground_truth": gt_summary,
                    "prediction": pred_summary
                })
                
                with open(results_file, "w") as f:
                    json.dump(existing_results, f, indent=4)
            else:
                print(f"  ⚠️ Skipped {item['id']}")
                
            # Fair cooldown for flagships
            time.sleep(15)
                
        if len(predictions) >= 3: # Calculate metrics if we have at least 3 samples
            print(f"  📊 Finalizing metrics for {model}...")
            rouge_output = rouge.compute(predictions=predictions, references=ground_truths)
            bert_output = bertscore.compute(predictions=predictions, references=ground_truths, lang="en")
            meteor_output = meteor.compute(predictions=predictions, references=ground_truths)

            existing_results["metrics"] = {
                "rouge": rouge_output,
                "bertscore_f1_avg": sum(bert_output['f1']) / len(bert_output['f1']),
                "meteor": meteor_output['meteor']
            }
            
            with open(results_file, "w") as f:
                json.dump(existing_results, f, indent=4)
            print(f"  🏁 Results saved to {results_file}")

if __name__ == "__main__":
    main()
