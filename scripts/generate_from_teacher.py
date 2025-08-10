import os
import json
import yaml
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from rich.console import Console
from dotenv import load_dotenv
console=Console()
load_dotenv()

hfKey=os.getenv('hf')
CONFIG_PATH = "..\configs\model_config.yaml"
CATEGORIES_PATH = "..\configs\categories.yaml"

with open(CONFIG_PATH, 'r') as file:
    cfg= yaml.safe_load(file)

TEACHER_MODEL = cfg['teacher']['model_name']
MAX_NEW_TOKEN =cfg['teacher']['max_new_tokens']
TEMPRATURE =cfg['teacher']['temperature']
DEVICE =cfg['teacher']['device']



console.print(f'Loading Teacher model {TEACHER_MODEL}',style='bold green')


tok=AutoTokenizer.from_pretrained(TEACHER_MODEL,trust_remote_code=True,cache_dir='D:\Models',use_auth_token=hfKey)
Qwen= AutoModelForCausalLM.from_pretrained(
    TEACHER_MODEL,
    trust_remote_code=True,
    device_map=DEVICE,
    cache_dir='D:\Models',
    use_auth_token=hfKey
)


def load_prompt_template(file_name):
    file_path = Path('prompts') / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt template file '{file_name}' not found.")
    return file_path.read_text(encoding='utf-8')

def generate_from_teacher(prompt):
    inputs= tok(prompt,return_tensors="pt").to(Qwen.device)
    output= Qwen.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKEN,
        temperature=TEMPRATURE,
        do_sample=True
    )

    return tok.decode(output[0], skip_special_tokens=True)

def run_gen(dataset_path, template_name,output_path,placeholder_name):

    template= load_prompt_template(template_name)
    output_records=[]


    if dataset_path.endswith(".jsonl"):
        with open(dataset_path, 'r', encoding='utf-8') as file:
            dataset=[json.loads(line) for line in file]
    elif dataset_path.endswith(".json"):
            dataset=[json.load(open(dataset_path))]
    else:
        raise ValueError("Unsupported dataset format. Please provide a .jsonl or .json file.")


    for i , sample in enumerate(dataset):
        prob_text=sample.get(placeholder_name.strip("{}"),"")
        if not prob_text:
            console.print(f"Warning: Placeholder '{placeholder_name}' not found in sample {i}.", style="bold yellow")
            continue

        prompt= template.replace(placeholder_name, prob_text)
        try:
            genCode= generate_from_teacher(prompt)
            output_records.append({"id":i,"input": prob_text, "output": genCode,category:template_name.replace(".txt","")})
            console.print(f"Generated code for sample {i}: {genCode}", style="bold green")
        except Exception as e:
            console.print(f"[Error] Failed to generate code for sample {i}: {e}", style="bold red")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as file:
        for record in output_records:
            file.write(json.dumps(record, ensure_ascii=False) + '\n')
    console.print(f"Finished processing. Output saved to {output_path}", style="bold green")


if __name__ == "__main__":
    run_gen(
        dataset_path="..\data\raw\HumanEval.json",
        template_name="python_application.txt",
        output_path="..\data\processed\curatedData.json",
        placeholder_name="{problem_statement}"
    )