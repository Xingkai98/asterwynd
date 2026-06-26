"""Build a single SWE-bench instance image."""
import sys
import logging
from datasets import load_dataset
from swebench.harness.docker_build import build_instance_images
from swebench.harness.constants import LATEST
import docker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("build")

instance_id = sys.argv[1] if len(sys.argv) > 1 else "psf__requests-1142"

logger.info("Loading cached dataset...")
ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
instances = [ex for ex in ds if ex["instance_id"] == instance_id]
if not instances:
    logger.error("Instance %s not found", instance_id)
    sys.exit(1)
logger.info("Building image for: %s", instance_id)

client = docker.from_env()
successful, failed = build_instance_images(
    client=client,
    dataset=instances,
    force_rebuild=False,
    max_workers=1,
    namespace="sweb.eval.x86_64",
    env_image_tag=LATEST,
    tag=LATEST,
)
logger.info("DONE — successful=%d failed=%d", len(successful), len(failed))
for s in successful:
    logger.info("  OK: %s", s)
for f in failed:
    logger.error("  FAIL: %s", f)
