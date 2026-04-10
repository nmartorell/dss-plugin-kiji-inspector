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
        self.kiji_home = os.environ.get("KIJI_HOME")  # set in code env resources
        self.pii_mappings = {}  # TODO: will this be retrieved from the proxy?

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
            LOGGER.info(
                "Query detected, masking user messages with Kiji: %s", user_messages
            )
            for message in user_messages:
                result = self._mask_pii(message.get("content", ""))
                if result["pii_found"]:
                    message["content"] = result["masked_message"]
                    self.pii_mappings.update(result["entities"])
                LOGGER.info("Kiji proxy masking result: %s", result)

        else:
            # Note: ugly repeating code, needs refactoring
            LOGGER.info("Response detected, de-masking with Kiji.")
            LOGGER.info("In-memory mappings: %s", self.pii_mappings)

            LOGGER.info("De-masking user messages: %s", user_messages)
            for message in user_messages:
                result = self._mask_pii(message.get("content", ""))
                if result["pii_found"]:
                    detected_entities = result["entities"].values()
                    demasked_message = result["masked_message"]
                    for entity in detected_entities:
                        demasked_message = demasked_message.replace(
                            entity, self.pii_mappings.get(entity, entity)
                        )
                    message["content"] = demasked_message

            LOGGER.info("De-masking AI response: %s", ai_response)
            result = self._mask_pii(ai_response.get("text", ""))
            if result["pii_found"]:
                detected_entities = result["entities"].values()
                demasked_message = result["masked_message"]
                for entity in detected_entities:
                    demasked_message = demasked_message.replace(
                        entity, self.pii_mappings.get(entity, entity)
                    )
                ai_response["text"] = demasked_message

            LOGGER.info("De-masked user messages: %s", user_messages)
            LOGGER.info("De-masked ai response: %s", ai_response)

        return input

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
            return (
                result.get("model_healthy") is True
                and result.get("status") == "healthy"
            )
        except Exception as exc:
            LOGGER.info("Kiji healthcheck failed: %s", exc)
            return False

    def _start_kiji_proxy(self):
        if not self.kiji_home:
            raise RuntimeError("KIJI_HOME is not configured")

        env = os.environ.copy()
        env["PROXY_PORT"] = f":{self.kiji_port}"

        command = [os.path.join(self.kiji_home, "bin", "kiji-proxy")]
        kiji_stdout_path = os.path.join(self.kiji_home, "kiji_proxy_stdout.log")
        kiji_stderr_path = os.path.join(self.kiji_home, "kiji_proxy_stderr.log")

        LOGGER.info("Starting Kiji proxy with command: %s", command)
        with (
            open(kiji_stdout_path, "w") as stdout,
            open(kiji_stderr_path, "w") as stderr,
        ):
            subprocess.Popen(
                command,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )

    def _mask_pii(self, message):
        return self._post_json("/api/pii/check", {"message": message})

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
