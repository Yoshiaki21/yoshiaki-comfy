import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// YoshiakiLoRACaptionLoad returns its image count via {"ui": {"text": [...]}}
// (see modules/yoshiaki_loracaption/lora_caption.py) so it never becomes a
// real output socket. ComfyUI doesn't generically render arbitrary "ui.text"
// on a node (unlike "ui.images"), so this adds a read-only display widget
// updated on every execution -- same pattern ComfyUI-Custom-Scripts' ShowText
// node uses.

app.registerExtension({
	name: "yoshiaki-comfy.loracaption",

	async beforeRegisterNodeDef(nodeType, nodeData, app) {
		if (nodeData.name !== "YoshiakiLoRACaptionLoad") return;

		const onExecuted = nodeType.prototype.onExecuted;
		nodeType.prototype.onExecuted = function (message) {
			onExecuted?.apply(this, arguments);

			// widgets[0] is the "path" input widget declared in INPUT_TYPES;
			// drop anything after it (a display widget from a previous run)
			// before adding a fresh one, so repeated executions don't pile up.
			if (this.widgets) {
				for (let i = 1; i < this.widgets.length; i++) {
					this.widgets[i].onRemove?.();
				}
				this.widgets.length = Math.min(this.widgets.length, 1);
			}

			const text = message?.text?.[0] ?? "";
			const widget = ComfyWidgets["STRING"](this, "image_count", ["STRING", { multiline: false }], app).widget;
			widget.inputEl.readOnly = true;
			widget.inputEl.style.opacity = 0.7;
			widget.value = text;
			widget.inputEl.value = text;

			this.onResize?.(this.size);
			this.graph?.setDirtyCanvas(true, true);
		};
	}
});
