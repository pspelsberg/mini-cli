import os
import sys
import argparse
import asyncio
import json
import logging

# Ensure root directory is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.memory import MemoryManager
from core.models import FileModification

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def parse_patch(patch_str: str) -> list[FileModification]:
    """Parses a git diff patch into a list of FileModification objects."""
    modifications = []
    current_file = None
    current_lines = []
    
    for line in patch_str.splitlines():
        if line.startswith("diff --git"):
            # New file block starts. Save previous file first.
            if current_file and current_lines:
                modifications.append(
                    FileModification(
                        filepath=current_file,
                        content="\n".join(current_lines),
                        is_new=False
                    )
                )
            current_file = None
            current_lines = []
        elif line.startswith("+++ b/"):
            # Extract filepath from the diff header
            path_part = line[6:].strip()
            # If there are tabs or space separated info, take the first part
            current_file = path_part.split()[0] if path_part else None
        elif current_file is not None:
            current_lines.append(line)
            
    if current_file and current_lines:
        modifications.append(
            FileModification(
                filepath=current_file,
                content="\n".join(current_lines),
                is_new=False
            )
        )
        
    # Fallback if no structured files found
    if not modifications and patch_str.strip():
        modifications.append(
            FileModification(
                filepath="patch.diff",
                content=patch_str,
                is_new=False
            )
        )
        
    return modifications


async def seed_rag(limit: int, offset: int, provider_name: str):
    print("Initializing MemoryManager...")
    # Initialize MemoryManager with standard global database path
    memory_manager = MemoryManager(provider_name=provider_name)
    
    print("Loading datasets library...")
    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: 'datasets' library is not installed. Please run 'pip install datasets'.")
        return
        
    print("Downloading SWE-bench Verified dataset from Hugging Face...")
    try:
        # Load test split which contains the verified evaluation tasks (500 samples)
        dataset = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return
        
    total_samples = len(dataset)
    if offset >= total_samples:
        print(f"Error: Offset {offset} is out of bounds (total samples: {total_samples}).")
        return
        
    num_to_seed = min(limit, total_samples - offset)
    print(f"Loaded dataset with {total_samples} samples. Seeding {num_to_seed} samples starting from index {offset}...")
    
    success_count = 0
    
    # Process each sample
    for idx in range(offset, offset + num_to_seed):
        sample = dataset[idx]
        instance_id = sample.get("instance_id", f"unknown_{idx}")
        problem_statement = sample.get("problem_statement", "")
        patch = sample.get("patch", "")
        
        if not problem_statement or not patch:
            print(f"[{idx+1}/{offset + num_to_seed}] Skipping {instance_id} due to missing data.")
            continue
            
        print(f"[{idx+1}/{offset + num_to_seed}] Processing {instance_id}...")
        
        # Parse patch into FileModification objects
        modifications = parse_patch(patch)
        
        # Add to memory
        task_desc = f"Fix issue {instance_id} in repository {sample.get('repo', '')}"
        success = await memory_manager.add_memory(
            task_description=task_desc,
            error_log=problem_statement,
            modifications=modifications
        )
        
        if success:
            success_count += 1
        else:
            print(f"  Warning: Failed to add {instance_id} to RAG database.")
            
    print(f"\nSeeding completed! Successfully seeded {success_count}/{num_to_seed} samples into the RAG database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed RAG database with SWE-bench Verified bugs and solutions.")
    parser.add_argument("--limit", type=int, default=100, help="Max number of samples to seed (default: 100).")
    parser.add_argument("--offset", type=int, default=0, help="Start index of samples to seed (default: 0).")
    parser.add_argument("--provider", type=str, default="ollama", help="Embedding provider name (default: ollama).")
    
    args = parser.parse_args()
    
    asyncio.run(seed_rag(args.limit, args.offset, args.provider))
