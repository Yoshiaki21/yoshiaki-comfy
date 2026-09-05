import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Standalone LoRA "info" dialog for YoshiakiWildcardEncode's "Select to add
// LoRA" combo. Inspired by rgthree-comfy's Power Lora Loader info button
// (https://github.com/rgthree/rgthree-comfy, MIT) but written from scratch
// and trimmed down -- see docs/yoshiaki/tasks_done.md for what's included
// vs intentionally left out (editable notes, custom video controls, the
// dev-mode menu, bulk model-management routes). Does not touch any of
// rgthree-comfy's own cache files.

const NO_LORA_SELECTED = "Select the LoRA to add to the text";

function el(tag, opts = {}) {
	const node = document.createElement(tag);
	if (opts.className) node.className = opts.className;
	if (opts.text != null) node.textContent = opts.text;
	if (opts.html != null) node.innerHTML = opts.html;
	if (opts.href != null) node.href = opts.href;
	if (opts.target != null) node.target = opts.target;
	if (opts.onclick) node.addEventListener("click", opts.onclick);
	for (const child of opts.children || []) node.appendChild(child);
	return node;
}

function render_trained_words(info) {
	const words = info.trainedWords || [];
	if (!words.length) {
		return el("div", { text: "(no trained words found)" });
	}

	const selected = new Set();
	const list = el("div", { className: "yoshiaki-lora-info-words" });

	const copy_button = (label, get_words) => {
		const btn = el("button", {
			text: label,
			onclick: async () => {
				const target_words = get_words();
				if (!target_words.length) return;
				await navigator.clipboard.writeText(target_words.join(", "));
				const original = btn.textContent;
				btn.textContent = "Copied!";
				setTimeout(() => { btn.textContent = original; }, 1200);
			},
		});
		return btn;
	};

	const copy_selected_btn = copy_button("Copy selected", () => [...selected]);
	const copy_all_btn = copy_button("Copy all", () => words.map((w) => w.word));
	const summary = el("span", { className: "yoshiaki-lora-info-words-summary" });

	function update_summary() {
		summary.textContent = selected.size ? `${selected.size} selected` : "";
		copy_selected_btn.disabled = selected.size === 0;
	}

	for (const w of words) {
		const label = w.count != null ? `${w.word} (${w.count})` : w.word;
		const chip = el("span", {
			className: "yoshiaki-lora-info-word",
			text: label,
			onclick: () => {
				if (selected.has(w.word)) {
					selected.delete(w.word);
					chip.classList.remove("-selected");
				} else {
					selected.add(w.word);
					chip.classList.add("-selected");
				}
				update_summary();
			},
		});
		list.appendChild(chip);
	}
	update_summary();

	return el("div", {
		children: [
			list,
			el("div", { className: "yoshiaki-lora-info-words-actions", children: [copy_selected_btn, copy_all_btn, summary] }),
		],
	});
}

function render_images(info) {
	const images = info.images || [];
	const gallery = el("div", { className: "yoshiaki-lora-info-gallery" });
	for (const img of images) {
		if (img.type === "video") {
			const video = document.createElement("video");
			video.src = img.url;
			video.controls = true;
			video.muted = true;
			gallery.appendChild(video);
		} else {
			const image_el = document.createElement("img");
			image_el.src = img.url;
			image_el.loading = "lazy";
			gallery.appendChild(image_el);
		}
	}
	return gallery;
}

function render_civitai_cell(container, lora_file, info) {
	if (info.civitaiLink) {
		return el("a", { text: "View on Civitai", href: info.civitaiLink, target: "_blank" });
	}
	if (info.civitaiError) {
		return el("span", { text: info.civitaiError });
	}
	const fetch_btn = el("button", {
		text: "Fetch info from Civitai",
		onclick: async () => {
			fetch_btn.disabled = true;
			fetch_btn.textContent = "Fetching...";
			try {
				const res = await api.fetchApi(`/yoshiaki/lora_info/refresh?file=${encodeURIComponent(lora_file)}`);
				const refreshed = await res.json();
				render_content(container, lora_file, refreshed);
			} catch (error) {
				fetch_btn.textContent = `Failed: ${error}`;
			}
		},
	});
	return fetch_btn;
}

function render_content(container, lora_file, info) {
	container.innerHTML = "";

	if (info.error) {
		container.appendChild(el("div", { text: info.error }));
		return;
	}

	const tags = el("div", { className: "yoshiaki-lora-info-tags" });
	if (info.type) tags.appendChild(el("span", { className: "yoshiaki-lora-info-tag", text: info.type }));
	if (info.baseModel) tags.appendChild(el("span", { className: "yoshiaki-lora-info-tag", text: info.baseModel }));
	container.appendChild(tags);

	const table = el("table", { className: "yoshiaki-lora-info-table" });
	const row = (label, value) => {
		const tr = el("tr", { children: [el("td", { text: label })] });
		const td = el("td");
		if (typeof value === "string") td.textContent = value;
		else td.appendChild(value);
		tr.appendChild(td);
		table.appendChild(tr);
	};
	row("File", lora_file);
	row("SHA256", info.sha256 || "");
	row("Civitai", render_civitai_cell(container, lora_file, info));
	container.appendChild(table);

	container.appendChild(el("h4", { text: "Trained Words" }));
	container.appendChild(render_trained_words(info));

	if ((info.images || []).length) {
		container.appendChild(el("h4", { text: "Sample Images" }));
		container.appendChild(render_images(info));
	}
}

async function open_lora_info_dialog(lora_file) {
	inject_css();

	const overlay = el("div", { className: "yoshiaki-lora-info-overlay" });
	const content = el("div", { className: "yoshiaki-lora-info-content", text: "Loading..." });
	const panel = el("div", {
		className: "yoshiaki-lora-info-panel",
		children: [
			el("div", {
				className: "yoshiaki-lora-info-header",
				children: [
					el("strong", { text: lora_file }),
					el("button", { className: "yoshiaki-lora-info-close", text: "×", onclick: () => overlay.remove() }),
				],
			}),
			content,
		],
	});

	overlay.appendChild(panel);
	overlay.addEventListener("click", (e) => {
		if (e.target === overlay) overlay.remove();
	});
	document.body.appendChild(overlay);

	try {
		const res = await api.fetchApi(`/yoshiaki/lora_info?file=${encodeURIComponent(lora_file)}`);
		const info = await res.json();
		render_content(content, lora_file, info);
	} catch (error) {
		content.textContent = `Failed to load LoRA info: ${error}`;
	}
}

let css_injected = false;
function inject_css() {
	if (css_injected) return;
	css_injected = true;
	document.head.appendChild(el("style", {
		html: `
.yoshiaki-lora-info-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 10000; display: flex; align-items: center; justify-content: center; }
.yoshiaki-lora-info-panel { background: #202020; color: #ddd; border-radius: 8px; width: min(700px, 90vw); max-height: 85vh; overflow-y: auto; padding: 16px; font-family: sans-serif; }
.yoshiaki-lora-info-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.yoshiaki-lora-info-close { background: none; border: none; color: #ddd; font-size: 20px; cursor: pointer; line-height: 1; }
.yoshiaki-lora-info-tags { margin-bottom: 8px; }
.yoshiaki-lora-info-tag { display: inline-block; background: #444; border-radius: 4px; padding: 2px 8px; margin-right: 6px; font-size: 12px; }
.yoshiaki-lora-info-table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
.yoshiaki-lora-info-table td { padding: 4px 8px; border-bottom: 1px solid #383838; vertical-align: top; font-size: 13px; }
.yoshiaki-lora-info-table td:first-child { color: #999; white-space: nowrap; width: 90px; }
.yoshiaki-lora-info-table a { color: dodgerblue; }
.yoshiaki-lora-info-words { display: flex; flex-wrap: wrap; align-content: flex-start; gap: 6px; margin-bottom: 6px; max-height: 220px; overflow-y: auto; padding: 4px; border: 1px solid #333; border-radius: 6px; }
.yoshiaki-lora-info-word { background: #333; border-radius: 12px; padding: 3px 10px; font-size: 12px; cursor: pointer; user-select: none; }
.yoshiaki-lora-info-word.-selected { background: dodgerblue; color: #fff; }
.yoshiaki-lora-info-words-actions { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.yoshiaki-lora-info-words-actions button { cursor: pointer; }
.yoshiaki-lora-info-gallery { display: flex; flex-wrap: wrap; gap: 8px; }
.yoshiaki-lora-info-gallery img, .yoshiaki-lora-info-gallery video { max-width: 200px; max-height: 200px; border-radius: 4px; }
`,
	}));
}

function move_widget_after(node, widget, after_widget) {
	const insert_idx = node.widgets.indexOf(after_widget) + 1;
	node.widgets.splice(node.widgets.indexOf(widget), 1);
	node.widgets.splice(insert_idx, 0, widget);
	node.setSize(node.computeSize());
}

app.registerExtension({
	name: "yoshiaki-comfy.lora_info",

	nodeCreated(node) {
		if (node.comfyClass !== "YoshiakiWildcardEncode") return;

		const lora_widget = node.widgets.find((w) => w.name === "Select to add LoRA");
		if (!lora_widget) return;

		const info_widget = node.addWidget("button", "LoRA Info", null, () => {
			const current = node._lora_value;
			if (!current || current === NO_LORA_SELECTED) {
				alert("Select a LoRA first.");
				return;
			}
			open_lora_info_dialog(current);
		});
		move_widget_after(node, info_widget, lora_widget);
	},
});
