"""Run Aider headlessly on SWE-bench instances directly on host (no Docker).

Bypasses the VFS Docker bottleneck. Clones repos via SSH, runs aider
headlessly, collects git diff, and writes predictions.jsonl compatible
with Claw-SWE-Bench format.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from datasets import load_dataset

AIDER_BIN = "/home/shared/agent-study/aider-venv/bin/aider"
AIDER_PYTHON = "/home/shared/agent-study/aider-venv/bin/python"
WORK_DIR = Path("/tmp/swebench-aider-host")
ARTIFACTS_DIR = Path("/home/shared/agent-study/my-agent/claw-swe-bench/artifacts/aider-host-50")
INSTANCE_FILE = Path("/home/shared/agent-study/my-agent/claw-swe-bench/config/verified_mini_50.txt")


def run(cmd, timeout=600, **kwargs):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, **kwargs)


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "sk-FKesXtdhmL1AG1ghAtWrprDeMmahvQUl1OjFGKehC5MzQhku")
    os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com/v1"

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Load instances
    with open(INSTANCE_FILE) as f:
        instance_ids = [line.strip() for line in f if line.strip()]

    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    instances = {ex["instance_id"]: ex for ex in ds if ex["instance_id"] in set(instance_ids)}

    # Clone repos (only once per repo)
    repos = {}
    for iid in instance_ids:
        ex = instances[iid]
        repo_name = ex["repo"]  # e.g. "django/django"
        if repo_name not in repos:
            repo_dir = WORK_DIR / repo_name.replace("/", "_")
            if not (repo_dir / ".git").exists():
                print(f"Cloning {repo_name}...")
                r = run(f"git clone git@github.com:{repo_name}.git {repo_dir}", timeout=600)
                if r.returncode != 0:
                    print(f"  FAILED: {r.stderr[:200]}")
                    # fallback to HTTPS
                    r = run(f"git clone https://github.com/{repo_name} {repo_dir}", timeout=600)
                    if r.returncode != 0:
                        print(f"  HTTPS also failed, skipping repo {repo_name}")
                        repos[repo_name] = None
                        continue
            repos[repo_name] = repo_dir

    # Run Aider on each instance
    predictions = []
    ok = 0
    fail = 0

    for idx, iid in enumerate(instance_ids, 1):
        ex = instances[iid]
        repo_name = ex["repo"]
        repo_dir = repos.get(repo_name)
        if repo_dir is None:
            print(f"[{idx}/{len(instance_ids)}] {iid} - SKIP (no repo)")
            fail += 1
            continue

        base_commit = ex["base_commit"]
        problem = ex["problem_statement"]
        artifact_dir = ARTIFACTS_DIR / iid
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Check if already done
        if (artifact_dir / "git.patch").exists():
            print(f"[{idx}/{len(instance_ids)}] {iid} - already done")
            predictions.append({
                "instance_id": iid,
                "model_name_or_path": "aider/deepseek-v4-pro",
                "model_patch": (artifact_dir / "git.patch").read_text(),
            })
            ok += 1
            continue

        print(f"[{idx}/{len(instance_ids)}] {iid} ...", end=" ", flush=True)

        # Reset repo to base commit
        run(f"cd {repo_dir} && git reset --hard {base_commit} && git clean -fd", timeout=60)

        # Write problem to file
        prompt_file = artifact_dir / "prompt.txt"
        prompt_file.write_text(problem)

        # Save full prompt for reference
        (artifact_dir / "prompt.txt").write_text(problem)

        # Run Aider
        t0 = time.time()
        r = run(
            f"cd {repo_dir} && "
            f"{AIDER_PYTHON} {AIDER_BIN} --yes --no-auto-commits --no-stream --no-suggest-shell-commands "
            f"--model openai/deepseek-v4-pro "
            f"--message-file {prompt_file}",
            timeout=600,
        )

        duration = time.time() - t0
        (artifact_dir / "agent_stdout.log").write_text(r.stdout or "")
        (artifact_dir / "agent_stderr.log").write_text(r.stderr or "")

        # Collect git diff
        r2 = run(f"cd {repo_dir} && git diff {base_commit}", timeout=60)
        patch = r2.stdout or ""

        (artifact_dir / "git.patch").write_text(patch)
        (artifact_dir / "metadata.json").write_text(json.dumps({
            "instance_id": iid,
            "duration_seconds": round(duration, 1),
            "patch_empty": not patch.strip(),
            "exit_code": r.returncode,
        }))

        predictions.append({
            "instance_id": iid,
            "model_name_or_path": "aider/deepseek-v4-pro",
            "model_patch": patch,
        })

        status = "patch_collected" if patch.strip() else "EMPTY"
        print(f"{status} ({duration:.0f}s)")
        ok += 1

    # Write predictions
    pred_path = ARTIFACTS_DIR / "predictions.jsonl"
    with open(pred_path, "w") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")

    print(f"\n=== Done: {ok} OK, {fail} failed ===")
    print(f"Predictions: {pred_path}")


if __name__ == "__main__":
    main()
