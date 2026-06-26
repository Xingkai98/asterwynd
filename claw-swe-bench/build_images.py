"""Build SWE-bench Docker images for verified_mini_50 instances."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import docker
from datasets import load_dataset
from swebench.harness.docker_build import build_instance_images

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build_images")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    # Load instance IDs from verified_mini_50.txt
    config_dir = Path(__file__).resolve().parent / "config"
    ids_file = config_dir / "verified_mini_50.txt"
    instance_ids = []
    with open(ids_file) as f:
        for line in f:
            line = line.strip()
            if line:
                instance_ids.append(line)

    logger.info("Loading SWE-bench Verified dataset from cache...")
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    instances = [ex for ex in ds if ex["instance_id"] in set(instance_ids)]

    # Sort by instance_id for deterministic ordering
    instances.sort(key=lambda x: x["instance_id"])
    logger.info("Will build %d images: %s ... %s", len(instances), instances[0]["instance_id"], instances[-1]["instance_id"])

    client = docker.from_env()
    build_instance_images(
        client=client,
        dataset=instances,
        force_rebuild=args.force,
        max_workers=args.max_workers,
        namespace="sweb.eval.x86_64",
        tag="latest",
    )
    logger.info("Build complete for %d images", len(instances))


if __name__ == "__main__":
    main()
