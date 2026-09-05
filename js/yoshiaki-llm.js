import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// YoshiakiLLMCaptionGenerator's `model` combo is populated once by
// `INPUT_TYPES` (server start / browser reload), and even then only from
// the hardcoded DEFAULT_LEMONADE_HOST/DEFAULT_LEMONADE_PORT in
// modules/yoshiaki_llm/llm_caption_node.py -- `INPUT_TYPES` is a
// classmethod with no access to any specific node's current
// lemonade_host/lemonade_port widget values. So editing those widgets (or
// loading a saved workflow that points at a different server) could never
// update `model` on its own. This asks modules/yoshiaki_llm/server.py to
// re-fetch the list against whatever host/port/api_key the node actually
// has, and swaps it into the combo in place.

const FALLBACK_MODEL_LABEL = "(Lemonade Server unavailable - check host/port)";

async function fetch_models(host, port, api_key) {
	const res = await api.fetchApi("/yoshiaki/llm/models", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ host, port, api_key }),
	});
	return await res.json();
}

function move_widget_after(node, widget, after_widget) {
	const insert_idx = node.widgets.indexOf(after_widget) + 1;
	node.widgets.splice(node.widgets.indexOf(widget), 1);
	node.widgets.splice(insert_idx, 0, widget);
	node.setSize(node.computeSize());
}

app.registerExtension({
	name: "yoshiaki-comfy.llm",

	nodeCreated(node) {
		if (node.comfyClass !== "YoshiakiLLMCaptionGenerator") return;

		const host_widget = node.widgets.find((w) => w.name === "lemonade_host");
		const port_widget = node.widgets.find((w) => w.name === "lemonade_port");
		const api_key_widget = node.widgets.find((w) => w.name === "lemonade_api_key");
		const model_widget = node.widgets.find((w) => w.name === "model");
		if (!host_widget || !port_widget || !model_widget) return;

		let refreshing = false;
		let refresh_button = null;

		async function refresh_models() {
			if (refreshing) return;
			refreshing = true;
			if (refresh_button) refresh_button.name = "Refreshing...";
			const previous_value = model_widget.value;
			try {
				const data = await fetch_models(host_widget.value, port_widget.value, api_key_widget?.value || "");
				const models = data.models || [];
				if (!models.length) return;
				model_widget.options.values = models;
				model_widget.value = models.includes(previous_value) ? previous_value : models[0];
			} catch (error) {
				console.error("[yoshiaki-comfy] Failed to refresh Lemonade model list:", error);
				model_widget.options.values = [FALLBACK_MODEL_LABEL];
				model_widget.value = FALLBACK_MODEL_LABEL;
			} finally {
				refreshing = false;
				if (refresh_button) refresh_button.name = "Refresh Models";
				node.graph?.setDirtyCanvas(true);
			}
		}

		// lemonade_host / lemonade_port / lemonade_api_key are plain text/int
		// widgets -- litegraph only invokes `.callback` when a value is
		// actually committed (blur/Enter for text, a changed number for INT),
		// not on every keystroke, so wrapping `.callback` here is safe from
		// request spam.
		for (const widget of [host_widget, port_widget, api_key_widget]) {
			if (!widget) continue;
			const original_callback = widget.callback;
			widget.callback = (...args) => {
				original_callback?.apply(widget, args);
				refresh_models();
			};
		}

		refresh_button = node.addWidget("button", "Refresh Models", null, () => refresh_models());
		move_widget_after(node, refresh_button, model_widget);

		// A saved workflow can point at a different lemonade_host/lemonade_port
		// than the defaults `model` was populated with at browser-reload time.
		// nodeCreated fires before ComfyUI applies the saved widgets_values
		// (node.configure() runs right after, synchronously), so read the
		// widgets on the next tick once the real restored values are in place.
		setTimeout(() => refresh_models(), 0);
	},
});
