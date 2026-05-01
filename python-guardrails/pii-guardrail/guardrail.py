import json
import logging
import os
import subprocess
import time

import requests
from dataiku.llm.guardrails import BaseGuardrail

LOGGER = logging.getLogger(__name__)


class CustomGuardrail(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config
        self.kiji_port = self.config.get("port", "9050")
        self.kiji_proxy = os.environ["KIJI_PROXY"]  # set in code env resources
        self.resources_dir = os.environ["RESOURCES_DIR"]  # set in code env resources
        self.pii_mappings = {}  # TODO: in future these will be retireved from the proxy

    def process(self, input, trace):
        # Start Kiji
        self._ensure_kiji_running()

        # Have we intercepted a query or response?
        is_query = "completionResponse" not in input

        # Extract user and ai messages
        user_messages = input.get("completionQuery", {}).get("messages", [])
        ai_response = input.get("completionResponse", {})

        # If it's a query, mask the pii in the messages; else revert the
        # pii detection.
        if is_query:
            LOGGER.info("Query detected, masking user messages with Kiji.")
            LOGGER.info("User messages to mask: %s", user_messages)

            for message in user_messages:
                raw_content = message.get("content", "")
                message["content"] = self._mask_pii(raw_content)

            LOGGER.info("Masked user messages: %s", user_messages)

        else:
            LOGGER.info("Response detected, de-masking AI response and user messages with Kiji.")
            LOGGER.info("User messages to de-mask: %s", user_messages)

            for message in user_messages:
                masked_content = message.get("content", "")
                message["content"] = self._demask_pii(masked_content)

            LOGGER.info("De-masked user messages: %s", user_messages)
            LOGGER.info("AI response to de-mask: %s", ai_response)

            masked_text = ai_response.get("text", "")
            ai_response["text"] = self._demask_pii(masked_text)

            LOGGER.info("De-masked ai response: %s", ai_response)

        return input

    def _mask_pii(self, message):
        result = self._post_json("/api/pii/check", {"message": message})
        if result["pii_found"]:
            message = result["masked_message"]
            self.pii_mappings.update(result["entities"])
        return message

    def _demask_pii(self, message):
        for masked_entity, demasked_entity in self.pii_mappings.items():
            message = message.replace(masked_entity, demasked_entity)
        return message

    def _ensure_kiji_running(self):
        if self._healthcheck():
            return

        self._start_kiji_proxy()

        # timeout in 10 s
        for _ in range(20):
            time.sleep(0.5)
            if self._healthcheck():
                return

        raise RuntimeError("Kiji proxy did not become healthy")

    def _healthcheck(self):
        try:
            result = self._post_json("/health", {})
            return result.get("model_healthy") is True and result.get("status") == "healthy"
        except Exception as exc:
            LOGGER.info("Kiji healthcheck failed: %s", exc)
            return False

    def _start_kiji_proxy(self):
        if not self.kiji_proxy:
            raise RuntimeError("KIJI_HOME is not configured")

        env = os.environ.copy()
        env["PROXY_PORT"] = f":{self.kiji_port}"

        kiji_stdout_path = os.path.join(self.resources_dir, "kiji_proxy_stdout.log")
        kiji_stderr_path = os.path.join(self.resources_dir, "kiji_proxy_stderr.log")

        LOGGER.info("Starting Kiji proxy with command: %s", self.kiji_proxy)
        with (
            open(kiji_stdout_path, "w") as stdout,
            open(kiji_stderr_path, "w") as stderr,
        ):
            subprocess.Popen(
                self.kiji_proxy,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )

    def _retrieve_pii_mappings(self):
        return self._post_json("/mappings", {})

    def _post_json(self, path, payload):
        url = "http://127.0.0.1:{}{}".format(self.kiji_port, path)
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            body = ""
            if exc.response is not None:
                body = exc.response.text
            raise RuntimeError("Kiji request failed: {} {}".format(url, body)) from exc

        body = response.text.strip()
        if not body:
            return {}

        return json.loads(body)
