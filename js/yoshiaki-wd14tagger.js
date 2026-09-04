import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
import { api } from "../../scripts/api.js";

// Trimmed from ComfyUI-WD14-Tagger's web/js/wd14tagger.js: only the
// progress badge (shown while a model auto-downloads) and the read-only
// "tags" display for YoshiakiWD14Tagger itself. The original's canvas-wide
// "right-click any image -> quick tag" context menu feature (patched into
// every other node type) was intentionally dropped -- unused, and removing
// it doesn't affect the node's own operation. See docs/yoshiaki/tasks_done.md.

const STATUS_SYMBOL = Symbol("yoshiaki-wd14tagger-status");

function getState(node) {
	return node[STATUS_SYMBOL] || {};
}

function setState(node, state) {
	node[STATUS_SYMBOL] = state;
	app.canvas.setDirty(true);
}

api.addEventListener("yoshiaki/wd14tagger/update_status", ({ detail }) => {
	const { node, progress, text } = detail;
	// Python omits `node` for the normal (in-graph) tagging path -- fall
	// back to whichever node is currently executing, same as upstream.
	const n = app.graph.getNodeById(+(node || app.runningNodeId));
	if (!n) return;
	const state = getState(n);
	state.status = Object.assign(state.status || {}, { progress: text ? progress : null, text: text || null });
	setState(n, state);
});

app.registerExtension({
	name: "yoshiaki-comfy.wd14tagger",

	async beforeRegisterNodeDef(nodeType, nodeData, app) {
		if (nodeData.name !== "YoshiakiWD14Tagger") return;

		const onDrawForeground = nodeType.prototype.onDrawForeground;
		nodeType.prototype.onDrawForeground = function (ctx) {
			const r = onDrawForeground?.apply?.(this, arguments);
			const state = getState(this);
			if (!state?.status?.text) {
				return r;
			}

			const { fgColor, bgColor, text, progress, progressColor } = { ...state.status };

			ctx.save();
			ctx.font = "12px sans-serif";
			const sz = ctx.measureText(text);
			ctx.fillStyle = bgColor || "dodgerblue";
			ctx.beginPath();
			ctx.roundRect(0, -LiteGraph.NODE_TITLE_HEIGHT - 20, sz.width + 12, 20, 5);
			ctx.fill();

			if (progress) {
				ctx.fillStyle = progressColor || "green";
				ctx.beginPath();
				ctx.roundRect(0, -LiteGraph.NODE_TITLE_HEIGHT - 20, (sz.width + 12) * progress, 20, 5);
				ctx.fill();
			}

			ctx.fillStyle = fgColor || "#fff";
			ctx.fillText(text, 6, -LiteGraph.NODE_TITLE_HEIGHT - 6);
			ctx.restore();
			return r;
		};

		const onExecuted = nodeType.prototype.onExecuted;
		nodeType.prototype.onExecuted = function (message) {
			const r = onExecuted?.apply?.(this, arguments);

			const pos = this.widgets.findIndex((w) => w.name === "tags");
			if (pos !== -1) {
				for (let i = pos; i < this.widgets.length; i++) {
					this.widgets[i].onRemove?.();
				}
				this.widgets.length = pos;
			}

			for (const list of message.tags) {
				const w = ComfyWidgets["STRING"](this, "tags", ["STRING", { multiline: true }], app).widget;
				w.inputEl.readOnly = true;
				w.inputEl.style.opacity = 0.6;
				w.value = list;
			}

			this.onResize?.(this.size);
			return r;
		};
	},
});
