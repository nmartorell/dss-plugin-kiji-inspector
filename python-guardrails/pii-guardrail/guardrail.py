# This file contains the implementation of the custom guardrail pii-guardrail
import logging
from dataiku.llm.guardrails import BaseGuardrail


class CustomGuardrail(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config

    def process(self, input, trace):
        if "completionResponse" in input:
            logging.info("response before processing:", input["completionResponse"]["text"])
            # do any processing and decide on an action here

        return input