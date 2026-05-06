import copy
import logging
import os

import kijiproxy as kiji
from dataiku.llm.guardrails import BaseGuardrail

LOGGER = logging.getLogger(__name__)


class CustomGuardrail(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config
        self.kiji_port = self.config.get("port", "9050")
        self.kiji_proxy = os.environ.get("KIJI_PROXY")
        self.pii_mappings = {}  # TODO: in future these will be retrieved from the proxy

        if not self.kiji_proxy:
            raise RuntimeError("KIJI_PROXY environment variable not set - has the plugin code environment been built?")

    def process(self, input, trace):
        # Start Kiji
        if not kiji.client.healthcheck(self.kiji_port):
            kiji.process.start(self.kiji_proxy, self.kiji_port)

        with trace.subspan("Kiji PII Guardrail") as span:
            # Have we intercepted a query or response?
            is_query = "completionResponse" not in input
            span.attributes["processing_phase"] = "query" if is_query else "response"

            # If query, mask the pii in the messages; else, revert the pii masking.
            if is_query:
                user_messages = input.get("completionQuery", {}).get("messages", [])

                LOGGER.info("Query detected, masking user messages with Kiji.")
                LOGGER.info("User messages to mask: %s", user_messages)

                span.attributes["original_user_messages"] = copy.deepcopy(user_messages)
                pii_found = False

                for message in user_messages:
                    raw_content = message.get("content", "")
                    masked_content, _pii_found = kiji.client.mask_pii(raw_content, self.pii_mappings, self.kiji_port)
                    message["content"] = masked_content
                    pii_found = pii_found or _pii_found

                if pii_found:
                    span.attributes["masked_user_messages"] = user_messages
                span.attributes["pii_found"] = pii_found

                LOGGER.info("Masked user messages: %s", user_messages)

            else:
                ai_response = input.get("completionResponse", {})

                LOGGER.info("Response detected, de-masking AI response with Kiji.")
                LOGGER.info("AI response to de-mask: %s", ai_response)

                masked_text = ai_response.get("text", "")
                demasked_text, pii_found = kiji.client.demask_pii(masked_text, self.pii_mappings)
                ai_response["text"] = demasked_text

                span.attributes["original_ai_response"] = masked_text
                span.attributes["pii_found"] = pii_found
                if pii_found:
                    span.attributes["demasked_ai_response"] = demasked_text

                LOGGER.info("De-masked ai response: %s", ai_response)

        return input
