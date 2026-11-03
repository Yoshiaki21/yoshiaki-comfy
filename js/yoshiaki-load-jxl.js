import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Frontend for YoshiakiLoadImageJXL (spec: docs/yoshiaki/JXL_Load_Node_指示書.md ch.3).
//
// The browser may not be able to show JPEG XL, so the preview is a WebP made by
// the server (/yoshiaki/jxl/preview) and the metadata comes from
// /yoshiaki/jxl/info. Both are fetched whenever the selected file changes, so the
// node shows the prompts before it is ever executed.
//
// Every widget added here is serialize=false: it is neither saved in the
// workflow's widgets_values nor sent in the prompt, so saved workflows never get
// their `image` value shifted.

const NODE_CLASS = "YoshiakiLoadImageJXL";
const STATE = Symbol("yoshiaki-load-jxl");

function markNotSerialized(widget) {
	widget.serialize = false;
	widget.options = widget.options || {};
	widget.options.serialize = false;
	return widget;
}

function addReadOnlyText(node, name, placeholder) {
	const widget = ComfyWidgets["STRING"](node, name, ["STRING", { multiline: true }], app).widget;
	markNotSerialized(widget);
	widget.value = "";
	if (widget.inputEl) {
		widget.inputEl.readOnly = true;
		widget.inputEl.placeholder = placeholder;
		widget.inputEl.style.opacity = 0.85;
	}
	return widget;
}

// ---------------------------------------------------------------------------
// summary text (spec 3.4)
// ---------------------------------------------------------------------------

function has(v) {
	return v !== null && v !== undefined && v !== "";
}

function fmtFloat(v) {
	if (typeof v !== "number") return String(v);
	return Number.isInteger(v) ? v.toFixed(1) : String(v);
}

function fmtDate(s) {
	const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)(Z|[+-]\d{2}:\d{2})?$/.exec(s);
	if (!m) return s;
	return m[3] ? `${m[1]} ${m[2]} ${m[3]}` : `${m[1]} ${m[2]}`;
}

function fmtModel(model) {
	if (model.kind !== "lora") return model.name;
	const sm = model.strength_model;
	const sc = model.strength_clip;
	if (has(sm) && has(sc)) return `${model.name} (lora ${fmtFloat(sm)}/${fmtFloat(sc)})`;
	const s = has(sm) ? sm : has(sc) ? sc : model.strength;
	return has(s) ? `${model.name} (lora ${fmtFloat(s)})` : `${model.name} (lora)`;
}

function buildSummary(info) {
	if (!info || info.status === "none") {
		const lines = ["XMPメタデータなし"];
		for (const w of info?.warnings || []) lines.push(`⚠ ${w}`);
		return lines.join("\n");
	}

	const lines = [];
	if (info.status === "unsupported_version") {
		lines.push(`⚠ 未対応のスキーマ v${info.schema_version}。読める範囲だけ表示`);
	} else if (info.status === "partial") {
		lines.push("簡易メタデータ（Parametersなし）");
	}

	if (has(info.seed)) {
		const src = info.seed_source;
		let where = "";
		if (src && (has(src.class_type) || has(src.node_id))) {
			where = ` (${[src.class_type, has(src.node_id) ? `#${src.node_id}` : null].filter(has).join(" ")})`;
		}
		lines.push(`seed: ${info.seed}${where}`);
	}

	const s = info.sampler || {};
	const sampler = [];
	if (has(s.steps)) sampler.push(`steps: ${s.steps}`);
	if (has(s.cfg)) sampler.push(`cfg: ${fmtFloat(s.cfg)}`);
	if (has(s.sampler_name)) sampler.push(`sampler: ${s.sampler_name}`);
	if (has(s.scheduler)) sampler.push(`scheduler: ${s.scheduler}`);
	if (has(s.denoise)) sampler.push(`denoise: ${fmtFloat(s.denoise)}`);
	if (sampler.length) lines.push(sampler.join(" / "));

	const img = info.image || {};
	if (has(img.width) && has(img.height)) {
		let enc = "";
		if (img.lossless === true) enc = " (lossless)";
		else if (has(img.quality)) enc = ` (quality ${img.quality})`;
		lines.push(`size: ${img.width} x ${img.height}${enc}`);
	}

	if (Array.isArray(info.models) && info.models.length) {
		lines.push(`models: ${info.models.map(fmtModel).join(" / ")}`);
	}
	if (has(info.created_at)) lines.push(`created: ${fmtDate(info.created_at)}`);
	if (has(info.note)) lines.push(`note: ${info.note}`);

	const g = info.generator;
	if (g && (has(g.node) || has(g.comfyui_version))) {
		const parts = [];
		if (has(g.node)) parts.push([g.node, g.node_version].filter(has).join(" "));
		if (has(g.comfyui_version)) parts.push(`ComfyUI ${g.comfyui_version}`);
		lines.push(`saved by: ${parts.join(" / ")}`);
	}
	if (has(info.schema_version)) lines.push(`schema: v${info.schema_version}`);

	for (const w of info.warnings || []) {
		if (info.status === "unsupported_version" && w.startsWith("unsupported schema version")) continue;
		lines.push(`⚠ ${w}`);
	}
	return lines.join("\n");
}

// ---------------------------------------------------------------------------
// node behaviour
// ---------------------------------------------------------------------------

function renderInfo(node, info) {
	const st = node[STATE];
	if (!st) return;
	st.positive.value = info?.positive || "";
	st.negative.value = info?.negative || "";
	st.summary.value = buildSummary(info);
	app.graph?.setDirtyCanvas(true, true);
}

function renderError(node, message) {
	const st = node[STATE];
	if (!st) return;
	st.positive.value = "";
	st.negative.value = "";
	st.summary.value = message;
	st.img.removeAttribute("src");
	st.img.style.display = "none";
	app.graph?.setDirtyCanvas(true, true);
}

async function updateFromFile(node) {
	const st = node[STATE];
	if (!st) return;
	const filename = st.imageWidget?.value;
	const token = ++st.token;
	if (!filename) {
		renderError(node, "ファイルが選択されていません");
		return;
	}
	const q = `filename=${encodeURIComponent(filename)}`;

	// Preview: the cache-busting token makes a re-selected (possibly replaced)
	// file load again; the server caches by path + mtime + size.
	st.img.style.display = "";
	st.img.src = api.apiURL(`/yoshiaki/jxl/preview?${q}&t=${Date.now()}`);

	try {
		const resp = await api.fetchApi(`/yoshiaki/jxl/info?${q}`, { cache: "no-store" });
		if (token !== st.token) return;
		if (!resp.ok) {
			renderError(node, `⚠ メタデータを取得できません (${resp.status}): ${await resp.text()}`);
			return;
		}
		renderInfo(node, await resp.json());
	} catch (e) {
		if (token === st.token) renderError(node, `⚠ メタデータを取得できません: ${e}`);
	}
}

async function refreshFileList(node) {
	const st = node[STATE];
	const resp = await api.fetchApi("/yoshiaki/jxl/list", { cache: "no-store" });
	if (!resp.ok) throw new Error(`list failed (${resp.status})`);
	const files = await resp.json();
	if (st?.imageWidget) st.imageWidget.options.values = files;
	return files;
}

async function uploadFile(node, file) {
	const st = node[STATE];
	if (!file.name.toLowerCase().endsWith(".jxl")) {
		alert("JXLファイル（.jxl）を選択してください");
		return;
	}
	const body = new FormData();
	body.append("image", file);
	body.append("type", "input");
	try {
		const resp = await api.fetchApi("/upload/image", { method: "POST", body });
		if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
		const data = await resp.json();
		const name = data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
		await refreshFileList(node);
		st.imageWidget.value = name;
		st.imageWidget.callback?.(name);
	} catch (e) {
		alert(`JXLのアップロードに失敗しました: ${e}`);
	}
}

function setupNode(node) {
	const imageWidget = node.widgets?.find((w) => w.name === "image");
	if (!imageWidget) return;

	// upload button (spec 3.3) -- standard image_upload is not used because its
	// preview relies on the browser displaying the original file.
	const fileInput = document.createElement("input");
	Object.assign(fileInput, { type: "file", accept: ".jxl", style: "display: none" });
	fileInput.addEventListener("change", () => {
		const file = fileInput.files?.[0];
		fileInput.value = "";
		if (file) uploadFile(node, file);
	});
	document.body.append(fileInput);
	const uploadWidget = node.addWidget("button", "upload_jxl", null, () => fileInput.click(), { serialize: false });
	uploadWidget.label = "JXLをアップロード";
	markNotSerialized(uploadWidget);

	// preview
	const container = document.createElement("div");
	Object.assign(container.style, {
		width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
		overflow: "hidden",
	});
	const img = document.createElement("img");
	Object.assign(img.style, { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" });
	img.addEventListener("error", () => { img.style.display = "none"; });
	img.addEventListener("load", () => { img.style.display = ""; });
	container.append(img);
	const previewWidget = node.addDOMWidget("jxl_preview", "yoshiaki-jxl-preview", container, {
		serialize: false,
		hideOnZoom: false,
		getMinHeight: () => 160,
	});
	markNotSerialized(previewWidget);

	node[STATE] = {
		token: 0,
		imageWidget,
		fileInput,
		img,
		positive: addReadOnlyText(node, "jxl_positive", "positive（読み取り専用）"),
		negative: addReadOnlyText(node, "jxl_negative", "negative（読み取り専用）"),
		summary: addReadOnlyText(node, "jxl_summary", "概要（読み取り専用）"),
	};

	const callback = imageWidget.callback;
	imageWidget.callback = function () {
		const r = callback?.apply(this, arguments);
		updateFromFile(node);
		return r;
	};

	const size = node.computeSize();
	node.setSize([Math.max(size[0], 360), Math.max(size[1], 640)]);
}

app.registerExtension({
	name: "yoshiaki-comfy.load-jxl",

	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_CLASS) return;

		const onNodeCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const r = onNodeCreated?.apply(this, arguments);
			setupNode(this);
			// a freshly placed node: show its default selection (onConfigure
			// re-runs this with the restored value when loading a workflow)
			requestAnimationFrame(() => updateFromFile(this));
			return r;
		};

		const onConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const r = onConfigure?.apply(this, arguments);
			requestAnimationFrame(() => updateFromFile(this));
			return r;
		};

		const onExecuted = nodeType.prototype.onExecuted;
		nodeType.prototype.onExecuted = function (message) {
			const r = onExecuted?.apply(this, arguments);
			const info = message?.jxl_info?.[0];
			if (info) {
				renderInfo(this, info);
				const st = this[STATE];
				if (st && !st.img.getAttribute("src")) updateFromFile(this);
			}
			return r;
		};

		const onRemoved = nodeType.prototype.onRemoved;
		nodeType.prototype.onRemoved = function () {
			this[STATE]?.fileInput?.remove();
			return onRemoved?.apply(this, arguments);
		};
	},
});
