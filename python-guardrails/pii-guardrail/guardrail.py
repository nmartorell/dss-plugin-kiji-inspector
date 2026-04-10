import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request

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
                message["content"] = result["masked_message"]
                LOGGER.info("Kiji proxy masking result: %s", result)

        else:
            # Note: ugly repeating code, needs refactoring
            LOGGER.info("Response detected, de-masking with Kiji. %s", user_messages)
            LOGGER.info("User messages to de-mask: %s", user_messages)
            LOGGER.info("AI response to de-mask: %s", ai_response)

            # demask user messages
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

            # demask
            result = self._mask_pii(ai_response.get("content", ""))
            if result["pii_found"]:
                detected_entities = result["entities"].values()
                demasked_message = result["masked_message"]
                for entity in detected_entities:
                    demasked_message = demasked_message.replace(
                        entity, self.pii_mappings.get(entity, entity)
                    )
                ai_response["content"] = demasked_message

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
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8").strip()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("Kiji request failed: {} {}".format(exc.code, body))

        if not body:
            return {}

        return json.loads(body)

    def _should_block(self, result):
        if not isinstance(result, dict):
            return False

        action = str(result.get("action", "")).upper()
        if action in {"BLOCK", "REJECT", "DENY"}:
            return True
        if action in {"PASS", "ALLOW", "OK"}:
            return False

        for key in (
            "blocked",
            "reject",
            "denied",
            "has_pii",
            "contains_pii",
            "pii_detected",
        ):
            if key in result:
                return bool(result[key])

        for key in ("allowed", "ok", "safe", "pass"):
            if key in result:
                return not bool(result[key])

        for key in ("entities", "recognizedEntities", "findings", "matches"):
            if isinstance(result.get(key), list) and len(result[key]) > 0:
                return True

        return False
