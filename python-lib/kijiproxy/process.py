import logging
import os
import subprocess
import time

from .client import healthcheck

LOGGER = logging.getLogger(__name__)


def start(kiji_path, kiji_port):
    env = os.environ.copy()
    env["PROXY_PORT"] = f":{kiji_port}"

    LOGGER.info("Starting Kiji proxy with command: %s", kiji_path)
    subprocess.Popen(
        kiji_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )

    # timeout in 10 s
    for _ in range(20):
        time.sleep(0.5)
        if healthcheck(kiji_port):
            return

    raise RuntimeError("Kiji proxy did not become healthy")
