"""Pull SWE-bench images from xuanyuan mirror and re-tag to expected format.

On Docker Hub: swebench/sweb.eval.x86_64.<instance_id>:latest
   e.g.: swebench/sweb.eval.x86_64.django__django-9296:latest

On Xuanyuan: docker.xuanyuan.run/swebench/sweb.eval.x86_64.<xuanyuan_id>:latest
   e.g.: docker.xuanyuan.run/swebench/sweb.eval.x86_64.django_1776_django-9296:latest

The instance_id uses __ (double underscore) as separator between repo and instance.
Xuanyuan replaces __ with _1776_.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

XUANYUAN_PREFIX = "docker.xuanyuan.run/swebench/sweb.eval.x86_64"
LOCAL_PREFIX = "sweb.eval.x86_64"
TAG = "latest"


def instance_id_to_xuanyuan(instance_id: str) -> str:
    """Convert instance_id to xuanyuan naming.

    django__django-9296 → django_1776_django-9296
    """
    return instance_id.replace("__", "_1776_")


def run_docker(*args, timeout=600):
    """Run docker command via sg docker."""
    cmd = " ".join(str(a) for a in args)
    return subprocess.run(
        ["sg", "docker", "-c", cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def main():
    ids_file = Path(__file__).resolve().parent / "config" / "verified_mini_50.txt"
    instance_ids = []
    with open(ids_file) as f:
        for line in f:
            line = line.strip()
            if line:
                instance_ids.append(line)

    print(f"Total instances: {len(instance_ids)}")

    ok = 0
    fail = 0

    for instance_id in instance_ids:
        xuanyuan_id = instance_id_to_xuanyuan(instance_id)
        xuanyuan_image = f"{XUANYUAN_PREFIX}.{xuanyuan_id}:{TAG}"
        local_image = f"{LOCAL_PREFIX}.{instance_id}:{TAG}"

        # Check if already exists locally
        r = run_docker("docker", "image", "inspect", local_image, timeout=30)
        if r.returncode == 0:
            print(f"  [{instance_id}] already exists")
            ok += 1
            continue

        # Pull from xuanyuan
        print(f"  [{instance_id}] pulling {xuanyuan_image} ...", end=" ", flush=True)
        r = run_docker("docker", "pull", xuanyuan_image, timeout=600)
        if r.returncode != 0:
            err = r.stderr.strip()[-200:]
            print(f"FAILED: {err}")
            fail += 1
            continue

        # Re-tag
        r2 = run_docker("docker", "tag", xuanyuan_image, local_image, timeout=60)
        if r2.returncode != 0:
            print(f"tag FAILED")
            fail += 1
            continue

        print("OK")
        ok += 1

    print(f"\n=== Done: {ok} OK, {fail} failed ===")


if __name__ == "__main__":
    main()
