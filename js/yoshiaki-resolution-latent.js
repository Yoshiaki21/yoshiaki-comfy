import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
	CUSTOM_LABEL,
	CalcError,
	compute,
	requiredMultiple,
} from "./yoshiaki-resolution-latent-calc.js";

// Frontend for YoshiakiResolutionLatent (spec: docs/yoshiaki/ResolutionLatent_Node_指示書.md ch.5).
//
// Python registers the aspect_ratio combo with the union of every preset's list
// (INPUT_TYPES is fixed at startup), so this extension swaps the list per model,
// fills in multiple / megapixels when the user changes the model, and shows a
// live size preview plus the actual result after execution.
//
// Loading a workflow only swaps the list: saved multiple / megapixels /
// aspect_ratio values are never overwritten.
//
// The display widget is serialize=false, so saved widgets_values never shift.

const NODE_CLASS = "YoshiakiResolutionLatent";
const UI_KEY = "yoshiaki_resolution_latent";
const STATE = Symbol("yoshiaki-resolution-latent");
const WATCHED = ["aspect_ratio", "custom_ratio", "orientation", "megapixels", "multiple", "batch_size"];

let presetsPromise = null;

function loadPresets() {
	if (!presetsPromise) {
		presetsPromise = api
			.fetchApi("/yoshiaki/resolution_latent/presets", { cache: "no-store" })
			.then((r) => {
				if (!r.ok) throw new Error(`HTTP ${r.status}`);
				return r.json();
			})
			.catch((e) => {
				console.error("[yoshiaki-comfy] ResolutionLatent: failed to load presets", e);
				presetsPromise = null; // retry on the next node
				return null;
			});
	}
	return presetsPromise;
}

function widget(node, name) {
	return node.widgets?.find((w) => w.name === name);
}

// A widget turned into a linked input: its value is not what will be used.
function isLinked(node, name) {
	return !!node.inputs?.some((i) => (i.widget?.name === name || i.name === name) && i.link != null);
}

function presetFor(data, name) {
	return data.presets.find((p) => p.name === name) || null;
}

// ---------------------------------------------------------------------------
// aspect-ratio list / auto fill
// ---------------------------------------------------------------------------

// userChange: the user picked another model -> also fill multiple / megapixels.
// Otherwise (node created / workflow loaded) only the list is swapped.
function applyModel(node, userChange) {
	const st = node[STATE];
	const data = st?.data;
	if (!data) return;
	st.loadWarnings = [];

	const modelW = widget(node, "model_preset");
	const aspectW = widget(node, "aspect_ratio");
	let preset = presetFor(data, modelW?.value);
	if (!preset) {
		preset = data.fallback;
		st.loadWarnings.push(`モデル '${modelW?.value}' がプリセットに無いため「${preset.name}」として扱います`);
	}
	st.preset = preset;

	if (aspectW && !isLinked(node, "aspect_ratio")) {
		const values = [...preset.aspect_ratios, CUSTOM_LABEL];
		const current = aspectW.value;
		if (!values.includes(current)) {
			if (userChange) {
				aspectW.value = values[0];
			} else if (current != null && current !== "") {
				// keep the saved value: add it to the list for now
				values.splice(values.length - 1, 0, current);
				st.loadWarnings.push(`保存されたアスペクト比 '${current}' は「${preset.name}」のリストにありません（一時的に追加）`);
			}
		}
		aspectW.options.values = values;
	}

	if (userChange) {
		const multW = widget(node, "multiple");
		const mpW = widget(node, "megapixels");
		if (multW && !isLinked(node, "multiple")) multW.value = preset.multiple;
		if (mpW && !isLinked(node, "megapixels")) mpW.value = preset.default_mp;
	}
	updateLive(node);
}

// ---------------------------------------------------------------------------
// display
// ---------------------------------------------------------------------------

function fmtShape(shape) {
	return shape.slice(1).join("×");
}

function updateLive(node) {
	const st = node[STATE];
	if (!st) return;
	st.exec = null; // inputs changed: the last execution result no longer applies

	const aspectW = widget(node, "aspect_ratio");
	const customW = widget(node, "custom_ratio");
	const isCustom = aspectW?.value === CUSTOM_LABEL;
	if (customW) customW.disabled = !isCustom && !isLinked(node, "aspect_ratio");

	const preset = st.preset;
	if (!preset) {
		st.live = st.data ? "" : "プリセットを読み込めませんでした（実行後に結果を表示）";
		st.liveWarnings = [];
		st.liveError = null;
		render(node);
		return;
	}

	const linked = ["aspect_ratio", "orientation", "megapixels", "multiple"].filter((n) => isLinked(node, n));
	if (isCustom && isLinked(node, "custom_ratio")) linked.push("custom_ratio");
	if (linked.length) {
		st.live = `リンク入力（${linked.join(", ")}）があるため、サイズは実行後に表示`;
		st.liveWarnings = [];
		st.liveError = null;
		render(node);
		return;
	}

	const spec = isCustom ? customW?.value ?? "" : aspectW?.value ?? "";
	const req = requiredMultiple(preset.multiple, preset.downscale, preset.generic);
	try {
		const r = compute(
			spec,
			widget(node, "orientation")?.value,
			Number(widget(node, "megapixels")?.value),
			Number(widget(node, "multiple")?.value),
			req,
			preset.mp_range
		);
		const d = preset.downscale;
		const latent = `${preset.latent_channels}×${r.height / d}×${r.width / d}`;
		const label = preset.generic ? "汎用・本体が自動補正" : "プリセット値";
		st.live = `${r.width} × ${r.height} ｜ ${r.mp.toFixed(2)} MP ｜ 潜在 ${latent}（${label}）`;
		st.liveWarnings = r.warnings;
		st.liveError = null;
	} catch (e) {
		st.live = "";
		st.liveWarnings = [];
		st.liveError = e instanceof CalcError ? e.message : String(e);
	}
	render(node);
}

function line(text, color) {
	const div = document.createElement("div");
	div.textContent = text;
	if (color) div.style.color = color;
	return div;
}

function render(node) {
	const st = node[STATE];
	if (!st) return;
	const el = st.el;
	el.replaceChildren();
	const warnColor = "#f0a030";
	const errColor = "#ff5555";

	if (st.exec) {
		const x = st.exec;
		el.append(line(`${x.width} × ${x.height} ｜ ${x.mp.toFixed(2)} MP ｜ 潜在 ${fmtShape(x.shape)}（${x.source}）`));
		el.append(line(`実行結果（プリセット: ${x.preset}、倍数 ${x.multiple}、バッチ ${x.shape[0]}）`, "#999"));
		for (const w of x.warnings || []) el.append(line(`⚠ ${w}`, warnColor));
	} else {
		if (st.live) el.append(line(st.live));
		if (st.liveError) el.append(line(`✖ ${st.liveError}`, errColor));
		for (const w of st.liveWarnings || []) el.append(line(`⚠ ${w}`, warnColor));
	}
	for (const w of st.loadWarnings || []) el.append(line(`⚠ ${w}`, warnColor));
	app.graph?.setDirtyCanvas(true, true);
}

// ---------------------------------------------------------------------------
// node setup
// ---------------------------------------------------------------------------

function setupNode(node) {
	const el = document.createElement("div");
	Object.assign(el.style, {
		fontSize: "12px",
		lineHeight: "1.4",
		padding: "2px 4px",
		whiteSpace: "pre-wrap",
		overflowY: "auto",
		width: "100%",
		height: "100%",
		boxSizing: "border-box",
	});
	const display = node.addDOMWidget("resolution_info", "yoshiaki-resolution-info", el, {
		serialize: false,
		hideOnZoom: false,
		getMinHeight: () => 56,
	});
	display.serialize = false;
	display.options = display.options || {};
	display.options.serialize = false;

	node[STATE] = {
		el,
		data: null,
		preset: null,
		live: "読み込み中…",
		liveWarnings: [],
		liveError: null,
		loadWarnings: [],
		exec: null,
	};

	const modelW = widget(node, "model_preset");
	if (modelW) {
		const cb = modelW.callback;
		modelW.callback = function () {
			const r = cb?.apply(this, arguments);
			applyModel(node, true);
			return r;
		};
	}
	for (const name of WATCHED) {
		const w = widget(node, name);
		if (!w) continue;
		const cb = w.callback;
		w.callback = function () {
			const r = cb?.apply(this, arguments);
			updateLive(node);
			return r;
		};
	}

	render(node);
	const size = node.computeSize();
	node.setSize([Math.max(size[0], 340), size[1]]);
}

async function attachPresets(node) {
	const data = await loadPresets();
	const st = node[STATE];
	if (!st) return;
	st.data = data;
	if (data) applyModel(node, false);
	else updateLive(node);
}

app.registerExtension({
	name: "yoshiaki-comfy.resolution-latent",

	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_CLASS) return;
		loadPresets();

		const onNodeCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const r = onNodeCreated?.apply(this, arguments);
			setupNode(this);
			attachPresets(this);
			return r;
		};

		// Workflow load: swap the list only (applyModel(node, false)); saved
		// values stay as they are.
		const onConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const r = onConfigure?.apply(this, arguments);
			attachPresets(this);
			return r;
		};

		const onConnectionsChange = nodeType.prototype.onConnectionsChange;
		nodeType.prototype.onConnectionsChange = function () {
			const r = onConnectionsChange?.apply(this, arguments);
			if (this[STATE]) requestAnimationFrame(() => updateLive(this));
			return r;
		};

		const onExecuted = nodeType.prototype.onExecuted;
		nodeType.prototype.onExecuted = function (message) {
			const r = onExecuted?.apply(this, arguments);
			const info = message?.[UI_KEY]?.[0];
			const st = this[STATE];
			if (info && st) {
				st.exec = info;
				render(this);
			}
			return r;
		};
	},
});
