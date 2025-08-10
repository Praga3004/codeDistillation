import argparse
import json 
import sys
from pathlib import Path
import yaml
import os
from dotenv import load_dotenv
CONFIG_PATH = "..\configs\model_config.yaml"
load_dotenv()
with open(CONFIG_PATH, 'r') as file:
    cfg= yaml.safe_load(file)

model_name = cfg['student']['model_name']
hfKey = os.getenv('hf')
try:
    from transformers import AutoTokenizer
except ImportError:
    print("Please install transformers: pip install transformers", file=sys.stderr)
    sys.exit(1)

def getTokenizer(model_name):
    tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True,cache_dir='D:\Models',use_auth_token=hfKey)
    return lambda text: len(tok.encode(text))

def count_tokensRecords(record,fields,tokenizer):
    total=0
    for f in fields:
        val=record.get(f,"")
        if isinstance(val,str):
            totol+=tokenizer(val)
        elif isinstance(val,list):
            totoal+=tokenizer("\n".join(map(str,val)))

        else:
            total+=tokenizer(str(val))
    return total


def processfile(inputPath,modelName,fields):
    inp=Path(inputPath)


    assert inp.exists() , f" input not found: {inp}"
    tokenizer = get_tokenizer(model_name)

    total_tokens = 0
    total_lines = 0
    min_tokens = None
    max_tokens = 0

    for line_no, line in enumerate(open(inp, "r", encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"[WARN] bad json at line {line_no}", file=sys.stderr)
            continue

        count = count_tokens_in_record(rec, fields, tokenizer)
        total_tokens += count
        total_lines += 1
        min_tokens = count if min_tokens is None else min(min_tokens, count)
        max_tokens = max(max_tokens, count)

        if line_no % 1000 == 0:
            print(f"[INFO] processed {line_no} lines... avg={total_tokens/total_lines:.1f} tokens")

    avg_tokens = total_tokens / total_lines if total_lines else 0

    print("------ TOKEN COUNT SUMMARY ------")
    print(f"File: {input_path}")
    print(f"Model: {model_name}")
    print(f"Fields: {fields}")
    print(f"Instances: {total_lines}")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Avg tokens per record: {avg_tokens:.1f}")
    print(f"Min tokens: {min_tokens}")
    print(f"Max tokens: {max_tokens}")
    print("---------------------------------")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="path to JSONL dataset")
    p.add_argument(
        "--fields", nargs="+", required=True,
        help="JSON fields to count tokens from (space-separated)"
    )
    args = p.parse_args()

    process_file(args.input, model_name, args.fields)


if __name__ == "__main__":
    main()

