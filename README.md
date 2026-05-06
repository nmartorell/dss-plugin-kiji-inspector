# Kiji Proxy DSS Plugin

This plugin adds a Dataiku DSS guardrail backed by the Kiji Privacy Proxy. It masks PII before LLM calls, then restores the original values in model responses so end users see the unmasked content again.

## Quickstart

1. Install the plugin in DSS.
2. Build the plugin code environment.
3. In your LLM Mesh setup, add the `Kiji Privacy Proxy` guardrail.

## Advanced

### Containerized Execution

If the guardrail will run in containers, the plugin code environment must also be built for those container configurations.

1. In DSS, go to `Administration -> Code Envs -> plugin_kiji-proxy_managed`.
2. Open the `Containerized execution` section.
3. Select the container configurations that should support this plugin code env.
4. Rebuild the code environment.

### Using A Custom PII Model

Custom PII models work both locally and in containers.

1. Train a custom Kiji PII model and publish the quantized ONNX model artifacts to a Hugging Face repo.
   The upstream Kiji Proxy customization flow is documented here:
   https://github.com/dataiku/kiji-proxy/blob/main/docs/07-customizing-pii-model.md
2. In DSS, open the plugin code environment `Resources` tab.
3. Set `CUSTOM_PII_MODEL_HF_REPO` to the Hugging Face repo id.
4. Optionally set `HF_TOKEN` if the repo is private.
5. Rebuild the code environment.

The downloaded model directory must contain:

- `model_quantized.onnx`
- `tokenizer.json`
- `label_mappings.json`
