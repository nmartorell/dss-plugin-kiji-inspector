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
        self.kiji_proxy = os.environ["KIJI_PROXY"]  # set in code env resources
        self.logs_dir = os.environ["RESOURCES_DIR"]  # set in code env resources
        self.pii_mappings = {}  # TODO: in future these will be retireved from the proxy

    def process(self, input, trace):
        # Start Kiji
        if not kiji.client.healthcheck(self.kiji_port):
            kiji.process.start(self.kiji_proxy, self.kiji_port, self.logs_dir)

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
                message["content"] = kiji.client.mask_pii(raw_content, self.pii_mappings, self.kiji_port)

            LOGGER.info("Masked user messages: %s", user_messages)

        else:
            LOGGER.info("Response detected, de-masking AI response and user messages with Kiji.")
            LOGGER.info("User messages to de-mask: %s", user_messages)

            for message in user_messages:
                masked_content = message.get("content", "")
                message["content"] = kiji.client.demask_pii(masked_content, self.pii_mappings)

            LOGGER.info("De-masked user messages: %s", user_messages)
            LOGGER.info("AI response to de-mask: %s", ai_response)

            masked_text = ai_response.get("text", "")
            ai_response["text"] = kiji.client.demask_pii(masked_text, self.pii_mappings)

            LOGGER.info("De-masked ai response: %s", ai_response)

        return input
