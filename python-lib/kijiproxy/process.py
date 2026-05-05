import logging
import os
import subprocess
import threading
import time

from .client import healthcheck

LOGGER = logging.getLogger(__name__)


def _forward_stream(stream, log_method, stream_name):
    try:
        for line in iter(stream.readline, ""):
            message = line.rstrip()
            if message:
                log_method("Kiji proxy %s: %s", stream_name, message)
    finally:
        stream.close()


def start(kiji_path, kiji_port):
    env = os.environ.copy()
    env["PROXY_PORT"] = f":{kiji_port}"

    LOGGER.info("Starting Kiji proxy with command: %s", kiji_path)
    process = subprocess.Popen(
        kiji_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
        text=True,
        bufsize=1,
    )
    threading.Thread(
        target=_forward_stream,
        args=(process.stdout, LOGGER.info, "stdout"),
        daemon=True,
    ).start()
    threading.Thread(
        target=_forward_stream,
        args=(process.stderr, LOGGER.warning, "stderr"),
        daemon=True,
    ).start()

    # timeout in 10 s
    for _ in range(20):
        time.sleep(0.5)
        if healthcheck(kiji_port):
            return

    raise RuntimeError("Kiji proxy did not become healthy")
