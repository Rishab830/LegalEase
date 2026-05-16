import json
import os
from datasets import load_dataset

def create_benchmark_dataset(num_samples=60, output_file="evaluation/benchmark_ground_truth.json"):
    print(f"Downloading {num_samples} samples from the BillSum dataset...")
    
    # Load the BillSum dataset
    dataset = load_dataset("billsum", split="test")
    
    benchmark_data = []
    
    # Take the first 'num_samples' documents
    for i, row in enumerate(dataset.select(range(num_samples))):
        ground_truth_structure = {
            "id": f"billsum_{i+1}",
            "document_text": row["text"],
            "expected_output": {
                "short_summary": row["summary"],
                "sections": {
                     "Purpose": "N/A", 
                     "Parties": "N/A", 
                     "Obligations": "N/A", 
                     "Duration": "N/A", 
                     "Termination": "N/A"
                },
                "clauses": []
            }
        }
        benchmark_data.append(ground_truth_structure)
        
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=4)
        
    print(f"✅ Saved {num_samples} samples to {output_file}")

if __name__ == "__main__":
    create_benchmark_dataset(num_samples=60)
