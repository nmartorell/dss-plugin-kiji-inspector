import json
import logging

import requests

LOGGER = logging.getLogger(__name__)


def healthcheck(kiji_port):
    try:
        result = _post_json("/health", {}, kiji_port)
        return result.get("model_healthy") is True and result.get("status") == "healthy"
    except Exception as exc:
        LOGGER.info("Kiji healthcheck failed: %s", exc)
        return False


def mask_pii(message, pii_mappings, kiji_port):
    result = _post_json("/api/pii/check", {"message": message}, kiji_port)
    if result["pii_found"]:
        message = result["masked_message"]
        pii_mappings.update(result["entities"])
    return message, result["pii_found"]


def demask_pii(message, pii_mappings):
    pii_found = False
    for masked_entity, demasked_entity in pii_mappings.items():
        if masked_entity in message:
            message = message.replace(masked_entity, demasked_entity)
            pii_found = True
    return message, pii_found


def _post_json(path, payload, kiji_port):
    url = "http://127.0.0.1:{}{}".format(kiji_port, path)
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
