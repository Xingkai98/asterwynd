"""Batch build SWE-bench instance images by running setup in containers.

Avoids Docker build (which OOMs with VFS driver) by using docker run + exec.
Environment images are deduplicated by script hash matching the swebench naming.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from datasets import load_dataset
from swebench.harness.constants import LATEST
from swebench.harness.test_spec.test_spec import make_test_spec

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("build_all")

BASE_IMAGE = "sweb.base.py.x86_64:latest"
DOCKER_NS = "sweb.eval.x86_64"


def run_docker(*args, check=True, timeout=300, input_text=None):
    """Run a docker command via sg docker."""
    cmd = ["sg", "docker", "-c", " ".join(f"'{a}'" if ' ' in a else a for a in args)]
    result = subprocess.run(
        ["sg", "docker", "-c", " ".join(args)],
        capture_output=True, text=True, timeout=timeout,
        input=input_text,
    )
    if check and result.returncode != 0:
        logger.error("Docker command failed: %s\nstderr: %s", " ".join(args[:5]), result.stderr[:500])
    return result


def build_env_image(env_image_key: str, setup_env_script: str, env_dockerfile: str) -> bool:
    """Build an environment image by running setup in a container and committing."""
    # Check if already exists
    result = run_docker("docker", "image", "inspect", env_image_key, check=False)
    if result.returncode == 0:
        logger.info("Env image %s already exists, skipping", env_image_key)
        return True

    logger.info("Building env image: %s", env_image_key)

    # Write setup script
    setup_path = f"/tmp/env_setup_{hashlib.md5(env_image_key.encode()).hexdigest()[:8]}.sh"
    with open(setup_path, "w") as f:
        f.write(setup_env_script)

    # Start container from base image
    container_name = f"env-build-{hashlib.md5(env_image_key.encode()).hexdigest()[:8]}"
    run_docker("docker", "rm", "-f", container_name, check=False)
    result = run_docker(
        "docker", "run", "-d", "--name", container_name,
        BASE_IMAGE, "sleep", "3600",
        timeout=120,
    )
    if result.returncode != 0:
        logger.error("Failed to start container for env image %s", env_image_key)
        return False

    # Copy setup script
    run_docker("docker", "cp", setup_path, f"{container_name}:/root/setup_env.sh", timeout=60)
    os.unlink(setup_path)

    # Run setup
    logger.info("Running env setup for %s...", env_image_key)
    result = run_docker(
        "docker", "exec", container_name,
        "bash", "-c",
        "chmod +x /root/setup_env.sh && source /opt/miniconda3/bin/activate && bash /root/setup_env.sh",
        timeout=600,
    )
    if result.returncode != 0:
        logger.error("Env setup failed for %s: %s", env_image_key, result.stderr[:500])
        # Try alternative without conda (apt-based Python install)
        logger.info("Trying alternative setup...")
        result2 = run_docker(
            "docker", "exec", container_name,
            "bash", "-c", (
                "apt-get update -qq && "
                "apt-get install -y -qq software-properties-common && "
                "add-apt-repository -y ppa:deadsnakes/ppa && "
                "apt-get update -qq && "
                "apt-get install -y -qq python3.9 python3.9-venv python3.9-dev && "
                "python3.9 -m venv /opt/testbed-venv && "
                "/opt/testbed-venv/bin/pip install pytest -q && "
                "mkdir -p /opt/miniconda3/envs/testbed/bin && "
                "ln -sf /opt/testbed-venv/bin/python /opt/miniconda3/envs/testbed/bin/python && "
                "ln -sf /opt/testbed-venv/bin/pip /opt/miniconda3/envs/testbed/bin/pip && "
                "ln -sf /opt/testbed-venv/bin/pytest /opt/miniconda3/envs/testbed/bin/pytest"
            ),
            timeout=600,
        )
        if result2.returncode != 0:
            logger.error("Alternative setup also failed for %s", env_image_key)
            run_docker("docker", "rm", "-f", container_name, check=False)
            return False

    # Commit
    run_docker("docker", "stop", container_name, timeout=60)
    run_docker("docker", "commit", container_name, env_image_key, timeout=120)
    run_docker("docker", "rm", "-f", container_name, check=False)
    logger.info("Env image built: %s", env_image_key)
    return True


def build_instance_image(instance_id: str, env_image_key: str, repo_script: str) -> bool:
    """Build an instance image from its env image."""
    image_name = f"{DOCKER_NS}.{instance_id}:latest"
    result = run_docker("docker", "image", "inspect", image_name, check=False)
    if result.returncode == 0:
        logger.info("Instance image %s already exists, skipping", image_name)
        return True

    logger.info("Building instance image: %s", image_name)

    # Write repo setup script
    script_hash = hashlib.md5(instance_id.encode()).hexdigest()[:8]
    setup_path = f"/tmp/repo_setup_{script_hash}.sh"
    with open(setup_path, "w") as f:
        f.write("#!/bin/bash\nset -euxo pipefail\n")
        f.write("\n".join(repo_script))
        f.write("\n")

    # Start container
    container_name = f"inst-build-{script_hash}"
    run_docker("docker", "rm", "-f", container_name, check=False)
    result = run_docker(
        "docker", "run", "-d", "--name", container_name,
        env_image_key, "sleep", "3600",
        timeout=120,
    )
    if result.returncode != 0:
        logger.error("Failed to start container for instance %s", instance_id)
        return False

    # Run repo setup
    run_docker("docker", "cp", setup_path, f"{container_name}:/root/setup_repo.sh", timeout=60)
    os.unlink(setup_path)

    logger.info("Running repo setup for %s...", instance_id)
    result = run_docker(
        "docker", "exec", container_name,
        "bash", "-c",
        "chmod +x /root/setup_repo.sh && source /opt/miniconda3/bin/activate && bash /root/setup_repo.sh",
        timeout=300,
    )
    if result.returncode != 0:
        logger.error("Repo setup failed for %s: %s", instance_id, result.stderr[:500])
        run_docker("docker", "rm", "-f", container_name, check=False)
        return False

    # Commit
    run_docker("docker", "stop", container_name, timeout=60)
    run_docker("docker", "commit", container_name, image_name, timeout=120)
    run_docker("docker", "rm", "-f", container_name, check=False)
    logger.info("Instance image built: %s", image_name)
    return True


def main():
    ids_file = Path(__file__).resolve().parent / "config" / "verified_mini_50.txt"
    instance_ids = []
    with open(ids_file) as f:
        for line in f:
            line = line.strip()
            if line:
                instance_ids.append(line)

    logger.info("Loading dataset (offline)...")
    os.environ["HF_HUB_OFFLINE"] = "1"
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    instances = {ex["instance_id"]: ex for ex in ds if ex["instance_id"] in set(instance_ids)}
    logger.info("Found %d instances in dataset", len(instances))

    # Phase 1: Build unique env images
    env_setups: dict[str, tuple] = {}  # env_image_key -> (setup_script, dockerfile, env_image_key)
    for iid in instance_ids:
        ex = instances.get(iid)
        if not ex:
            logger.warning("Instance %s not found in dataset", iid)
            continue
        spec = make_test_spec(ex, namespace=DOCKER_NS, env_image_tag=LATEST, instance_image_tag=LATEST)
        env_setups[spec.env_image_key] = (spec.setup_env_script, spec.env_dockerfile, spec.env_image_key)

    logger.info("Phase 1: Building %d unique env images", len(env_setups))
    env_success = {}
    for env_key, (setup_script, dockerfile, _) in env_setups.items():
        ok = build_env_image(env_key, setup_script, dockerfile)
        env_success[env_key] = ok
        if not ok:
            logger.warning("Env image %s failed — instances depending on it will fail", env_key)

    # Phase 2: Build instance images
    logger.info("Phase 2: Building %d instance images", len(instance_ids))
    ok_count = 0
    fail_count = 0
    for iid in instance_ids:
        ex = instances.get(iid)
        if not ex:
            continue
        spec = make_test_spec(ex, namespace=DOCKER_NS, env_image_tag=LATEST, instance_image_tag=LATEST)
        if not env_success.get(spec.env_image_key):
            logger.warning("Skipping %s — env image %s failed", iid, spec.env_image_key)
            fail_count += 1
            continue
        ok = build_instance_image(iid, spec.env_image_key, spec.repo_script_list)
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    logger.info("=== Build complete: %d OK, %d failed ===", ok_count, fail_count)


if __name__ == "__main__":
    main()
