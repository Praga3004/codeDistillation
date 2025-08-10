#!/usr/bin/env python3
"""
build_final_dataset.py
- Merge generated teacher model outputs into one clean dataset
- Deduplicate, filter, shuffle, and split into train/eval sets
"""

import argparse
import json
import random
from pathlib import Path
from typing import List, Dict, Any


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                data.append(rec)
            except json.JSONDecodeError:
                print(f"[WARN] Skipping bad JSON at {path}:{line_no}")
    return data


def save_jsonl(path: Path, data: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        for rec in data:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def basic_filter(record: Dict[str, Any], min_len: int = 20) -> bool:
    """
    Returns True if record passes basic checks:
    - Required keys present
    - Non-empty prompt and completion
    - Completion length above min_len
    """
    if "prompt" not in record or "completion" not in record:
        return False
    if not record["prompt"].strip() or not record["completion"].strip():
        return False
    if len(record["completion"]) < min_len:
        return False
    return True


def deduplicate(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for r in records:
        key = (r.get("prompt", "").strip(), r.get("completion", "").strip())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs", nargs="+", required=True,
        help="List of JSONL files to merge"
    )
    parser.add_argument(
        "--output_dir", type=str, required=True,
        help="Where to save final train/eval files"
    )
    parser.add_argument(
        "--eval_ratio", type=float, default=0.02,
        help="Fraction of data to reserve for evaluation"
    )
    parser.add_argument(
        "--min_completion_len", type=int, default=20,
        help="Minimum length of completion text"
    )
    parser.add_argument(
        "--shuffle_seed", type=int, default=42,
        help="Random seed for shuffling"
    )
    args = parser.parse_args()

    all_records = []
    for in_file in args.inputs:
        path = Path(in_file)
        if not path.exists():
            print(f"[WARN] File not found: {in_file}")
            continue
        recs = load_jsonl(path)
        print(f"[INFO] Loaded {len(recs)} from {in_file}")
        all_records.extend(recs)

    # Basic filtering
    filtered = [r for r in all_records if basic_filter(r, args.min_completion_len)]
    print(f"[INFO] Filtered down to {len(filtered)} after quality checks")

    # Deduplicate
    deduped = deduplicate(filtered)
    print(f"[INFO] Deduplicated to {len(deduped)} unique records")

    # Shuffle
    random.seed(args.shuffle_seed)
    random.shuffle(deduped)

    # Split
    eval_size = int(len(deduped) * args.eval_ratio)
    eval_set = deduped[:eval_size]
    train_set = deduped[eval_size:]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    save_jsonl(output_dir / "train.jsonl", train_set)
    save_jsonl(output_dir / "eval.jsonl", eval_set)

    print(f"[INFO] Saved train set: {len(train_set)} records")
    print(f"[INFO] Saved eval set: {len(eval_set)} records")
    print("[DONE] Dataset build complete.")


if __name__ == "__main__":
    main()
