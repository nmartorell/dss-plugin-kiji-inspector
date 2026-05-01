import logging
import os
import subprocess
import time

from .client import healthcheck

LOGGER = logging.getLogger(__name__)


def start(kiji_path, kiji_port, logs_dir):
    env = os.environ.copy()
    env["PROXY_PORT"] = f":{kiji_port}"

    kiji_stdout_path = os.path.join(logs_dir, "kiji_proxy_stdout.log")
    kiji_stderr_path = os.path.join(logs_dir, "kiji_proxy_stderr.log")

    LOGGER.info("Starting Kiji proxy with command: %s", kiji_path)
    with (
        open(kiji_stdout_path, "w") as stdout,
        open(kiji_stderr_path, "w") as stderr,
    ):
        subprocess.Popen(
            kiji_path,
            stdout=stdout,
            stderr=stderr,
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
