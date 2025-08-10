import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple,Optional





DEFAULT_TIMEOUT_SEC=10
BANNED_IMPORTS={
    "socket", "requests", "urllib", "http", "ftplib",
    "subprocess", "multiprocessing", "threading", "asyncio",
    "os", "shutil", "pathlib", "paramiko",
    "psutil",
}

BANNED_APIS={
     "os.system(", "os.remove(", "os.rmdir(", "shutil.rmtree(",
    "subprocess.run(", "subprocess.Popen(", "eval(", "exec(",
    "__import__(", "open("/**/")",
}


MAX_CODE_CHARS = 100_000

TEST_START_PATTERN = [
    r"^\s*#\s*tests?\b",
    r"^\s*#\s*unit[-\s]?tests?\b",
    r"^\s*import\s+pytest\b",
    r"^\s*from\s+pytest\s+import\b",
    r"^\s*class\s+Test\w*\(",
    r"^\s*def\s+test_",
    r"^\s*if\s+__name__\s*==\s*[\"']__main__[\"']\s*:",
]


FENCE_RE = re.compile(r"```(?:python)?\s*([\s\S]*?)```", re.IGNORECASE)
LINE_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in TEST_START_PATTERNS]


def strip_code_fences(text):
    blocks=FENCE_RE.findall(text or "")
    if blocks:
        return "\n".join(b.strip() for b in blocks if b.strip()) 
    return text or ""



def splite_code_and_tests(text):
    raw= text or ""
    idx=None
    for path in LINE_PATTERNS:
        m=pat.search(raw)
        if m:
            idx=m.start()
            break

    if idx is None:
        code=raw
        tests=(
            "import importlib.util, types, sys\n"
            "spec = importlib.util.spec_from_file_location('solution', 'solution.py')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "def test_smoke():\n"
            "    assert mod is not None\n"
        )
        return code,tests

    code=raw[:idx].strip()
    tests=raw[idx:].strip()
    return code, tests

def looks_unsafe(src):
    if len(src) > MAX_CODE_CHARS:
        return f"code too large ({len(src)} chars)"
    flat=src

    for name in BANNED_IMPORTS:
        if re.search(rf"^\s*(from|import)\s+{re.escape(name)}\b", flat, re.MULTILINE):
            return f"banned import: {name}"
    for api in BANNED_APIS:
        if api == 'open("/**/")':
            if re.search(r'open\(\s*["\']\/', flat):
                return "banned open on absolute path"
            if re.search(r'open\(\s*["\'][^"\']+["\']\s*,\s*["\']w', flat):
                return "banned open in write mode"
        else:
            if api in flat:
                return f"banned api: {api}"

    return None



        
def run_pytext_in_sandbox(code,tests,timeout:DEFAULT_TIMEOUT_SEC):

    with tempfile.TemporaryDirectory() as td:
        td_path=Path(td)
        (td_path/"solution.py").write_text(code,encoding="utf-8")

        testBody = tests

        if "import solution" not in testBody and "from solution" not in testBody:
            testBody = f"import solution\n {tests}"

        (td_path/"test_solution.py").write_text(testBody,encoding="utf-8")

        (td_path/"pytest.ini").write_text("[pytest]\naddopts = --maxfail=1 --disable-warnings -q\n",encoding="utf-8")


        env = os.environ.copy()

        for k in list(env.keys()):
            if k.lower().endswith("_proxy") or k.lower() in {"http_proxy","https_proxy"}:
                env.pop(k,None)

        try:
            start = time.time()
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "q"],
                cwd= str(td_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=Fasle,
                text=True
            )
            dur_ms= int((time.time()-start) * 1000)
            ok = proc.returncode == 0
            logs = proc.stdout or ""
            logs = f"[duration_ms={dur_ms}] " + logs
            return ok, logs
        except subprocess.TimeoutExpired as e:
            return False, f"[timeout after {timeout_sec}s] {e}"
        except Exception as e:
            return False, f"[error] {e}"
        

def try_fromat_lint(td):
    def exists(cmd):
        try:
            subprocess.run([cmd,"--version"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
    if exists("black"):
        try:
            subprocess.run(["black",str(td)],check=True)
        except Exception as e:
            print(f"[Error] Failed to format with black: {e}")
            pass
    if exists("ruff"):
        try:
            subprocess.run(["ruff", "check", "--fix", "."], cwd=str(td), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def extract_output_text(rec):
    if "output" in rec and isinstq(rec['output'],str):
        return rec["output"]
    if "teacher_solution" in rec and isinstance(rec['teacher_solution'], str):
        return rec["teacher_solution"]
    parts=[]
    for k in ("code","solution","text"):
        v= rec.get(k)
        if isinstacne(v,str):
            parts.append
    return "\n\n".join(parts)
def process_file(input_path: str, output_path: str, timeout_sec: int) -> None:
    inp = Path(input_path)
    assert inp.exists(), f"input not found: {inp}"

    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    kept = 0
    total = 0

    with open(output_path, "w", encoding="utf-8") as fout:
        with open(input_path, "r", encoding="utf-8") as fin:
            for line_no, line in enumerate(fin, 1):
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[WARN] bad json at line {line_no}, skipping")
                    continue

                raw = extract_output_text(rec)
                if not raw:
                    print(f"[WARN] empty output at #{line_no}, skipping")
                    continue

                payload = strip_code_fences(raw)
                code, tests = split_code_and_tests(payload)

                # Safety checks (code only; tests may import pytest)
                reason = looks_unsafe(code)
                if reason:
                    rec["verify_status"] = "rejected_unsafe"
                    rec["verify_reason"] = reason
                    continue

                ok, logs = run_pytest_in_sandbox(code, tests, timeout_sec=timeout_sec)
                if not ok:
                    rec["verify_status"] = "rejected_fail"
                    rec["verify_logs"] = logs[-4000:]  # clip
                    continue

                # Accepted
                rec["verify_status"] = "accepted"
                rec["code"] = code
                rec["tests"] = tests
                rec["verify_logs"] = logs[-2000:]  # keep short
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1

                if kept % 50 == 0:
                    print(f"[OK] kept={kept} / total={total}")

    print(f"[DONE] kept={kept} / seen={total} -> {output_path}")



def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="path to generated JSONL from teacher")
    p.add_argument("--output", required=True, help="path to save passing filtered JSONL")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="pytest timeout seconds per sample")
    args = p.parse_args()

    process_file(args.input, args.output, timeout_sec=args.timeout)


if __name__ == "__main__":
    main()


