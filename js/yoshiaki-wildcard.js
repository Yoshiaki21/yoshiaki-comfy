import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Trimmed from ComfyUI-Impact-Pack's js/impact-pack.js: only the wildcard
// combo box + LoRA combo box + mode-widget behavior needed for
// YoshiakiWildcardProcessor / YoshiakiWildcardEncode, plus a folder filter
// for both the wildcard combo and the LoRA combo (added later -- see
// docs/yoshiaki/tasks_done.md).

let wildcards_list = [];

const WILDCARD_LABEL = "Select the Wildcard to add to the text";
const LORA_LABEL = "Select the LoRA to add to the text";
const NO_FOLDER_LABEL = "(no folder)";
const WILDCARD_FOLDER_STORAGE_PREFIX = "yoshiaki-wildcard-folder:";
const LORA_FOLDER_STORAGE_PREFIX = "yoshiaki-lora-folder:";

async function load_wildcards() {
	try {
		// /refresh rescans the wildcards folder(s) on disk before returning
		// the list (same data shape as /list), so a page reload always picks
		// up files added/removed since the server started.
		let res = await api.fetchApi('/yoshiaki/wildcards/refresh');
		let data = await res.json();
		wildcards_list = data.data;
	} catch (error) {
		console.error('[yoshiaki-comfy] Failed to load wildcard list:', error);
	}
}

load_wildcards();

// --- generic folder helpers -------------------------------------------
// `items` is a flat array (wildcard entries, LoRA filenames, ...) and
// `get_path` extracts a '/'-separated relative path from one item (with
// no leading/trailing slashes). Folder paths are enumerated at every
// nesting level, flattened -- e.g. "a/b/c" contributes both "a" and "a/b".

function folders_from_items(items, get_path) {
	const folders = new Set();
	for (const item of items) {
		const parts = get_path(item).split('/');
		for (let i = 1; i < parts.length; i++) {
			folders.add(parts.slice(0, i).join('/'));
		}
	}
	return [NO_FOLDER_LABEL, ...Array.from(folders).sort()];
}

// Items whose immediate parent folder is exactly `folder` (NO_FOLDER_LABEL
// => items directly at the root, no subfolder).
function items_in_folder(items, get_path, folder) {
	return items.filter(item => {
		const parts = get_path(item).split('/');
		const parent = parts.slice(0, -1).join('/');
		return folder === NO_FOLDER_LABEL ? parent === '' : parent === folder;
	});
}

// The first folder (in folders_from_items() order) that actually has at
// least one item directly under it. Falls back to NO_FOLDER_LABEL if
// nothing has any entries at all.
function default_folder(items, get_path) {
	for (const folder of folders_from_items(items, get_path)) {
		if (items_in_folder(items, get_path, folder).length > 0) return folder;
	}
	return NO_FOLDER_LABEL;
}

function load_stored_folder(prefix, node) {
	try {
		return localStorage.getItem(prefix + node.id);
	} catch (error) {
		return null;
	}
}

function save_stored_folder(prefix, node, folder) {
	try {
		localStorage.setItem(prefix + node.id, folder);
	} catch (error) {
		// localStorage unavailable (private browsing, etc.) -- selection just won't persist.
	}
}

// Resolves the folder a node should start with: the stored selection if
// it's still non-empty, otherwise the best default.
function initial_folder(prefix, node, items, get_path) {
	const stored = load_stored_folder(prefix, node);
	if (stored && items_in_folder(items, get_path, stored).length > 0) {
		return stored;
	}
	return default_folder(items, get_path);
}

// Inserts `widget` (just appended via node.addWidget, so currently last)
// to sit directly above `before_widget` in the node's widget list.
function move_widget_above(node, widget, before_widget) {
	const insert_before_idx = node.widgets.indexOf(before_widget);
	node.widgets.pop();
	node.widgets.splice(insert_before_idx, 0, widget);
	node.setSize(node.computeSize());
}

// entry looks like "__folder/sub/name__" (or "__name__" with no folder).
const wildcard_entry_path = (entry) => entry.slice(2, -2);
// LoRA filenames from folder_paths.get_filename_list() may use OS-native
// separators on Windows -- normalize to '/' before splitting.
const lora_entry_path = (entry) => entry.replace(/\\/g, '/');

api.addEventListener("yoshiaki-node-feedback", ({ detail }) => {
	const node = app.graph.getNodeById(Number(detail.node_id));
	if (!node) return;
	const widget = node.widgets?.find(w => w.name === detail.widget_name);
	if (!widget) return;
	widget.value = detail.value;
	node.graph?.setDirtyCanvas(true);
});

app.registerExtension({
	name: "yoshiaki-comfy.wildcard",

	commands: [
		{
			id: 'refresh-yoshiaki-wildcard',
			label: 'Yoshiaki: Refresh Wildcard List',
			function: async () => {
				await load_wildcards();
			}
		}
	],

	menuCommands: [
		{
			path: ['Yoshiaki'],
			commands: ['refresh-yoshiaki-wildcard']
		}
	],

	nodeCreated(node, app) {
		if (node.comfyClass !== "YoshiakiWildcardEncode" && node.comfyClass !== "YoshiakiWildcardProcessor") {
			return;
		}

		const has_lora = node.comfyClass === "YoshiakiWildcardEncode";

		const wildcard_text_widget = node.widgets.find(w => w.name === 'wildcard_text');
		const populated_text_widget = node.widgets.find(w => w.name === 'populated_text');
		const mode_widget = node.widgets.find(w => w.name === 'mode');
		const wildcard_widget = node.widgets.find(w => w.name === 'Select to add Wildcard');
		const lora_widget = has_lora ? node.widgets.find(w => w.name === 'Select to add LoRA') : null;

		// --- LoRA folder filter (YoshiakiWildcardEncode only), inserted
		// directly above the LoRA combo. Must run before the wildcard-folder
		// block below so lora_widget's original (unfiltered) options.values --
		// the full list Python supplied via folder_paths.get_filename_list()
		// -- is captured before anything else touches this node's widgets.
		let lora_list = [];
		if (has_lora) {
			lora_list = lora_widget.options.values.filter(v => v !== LORA_LABEL);

			node._lora_folder = initial_folder(LORA_FOLDER_STORAGE_PREFIX, node, lora_list, lora_entry_path);

			const lora_folder_widget = node.addWidget(
				'combo',
				'LoRA Folder',
				node._lora_folder,
				(value) => {
					node._lora_folder = value;
					save_stored_folder(LORA_FOLDER_STORAGE_PREFIX, node, value);
				},
				{ values: folders_from_items(lora_list, lora_entry_path) }
			);
			Object.defineProperty(lora_folder_widget.options, "values", {
				set: () => {},
				get: () => folders_from_items(lora_list, lora_entry_path)
			});
			move_widget_above(node, lora_folder_widget, lora_widget);
		}

		// --- Wildcard folder filter, inserted directly above the wildcard combo ---
		node._wildcard_folder = initial_folder(WILDCARD_FOLDER_STORAGE_PREFIX, node, wildcards_list, wildcard_entry_path);

		const wildcard_folder_widget = node.addWidget(
			'combo',
			'Wildcard Folder',
			node._wildcard_folder,
			(value) => {
				node._wildcard_folder = value;
				save_stored_folder(WILDCARD_FOLDER_STORAGE_PREFIX, node, value);
			},
			{ values: folders_from_items(wildcards_list, wildcard_entry_path) }
		);
		Object.defineProperty(wildcard_folder_widget.options, "values", {
			set: () => {},
			get: () => folders_from_items(wildcards_list, wildcard_entry_path)
		});
		move_widget_above(node, wildcard_folder_widget, wildcard_widget);

		// --- wildcard combo: insert selected value into wildcard_text, filtered by folder ---
		// NOTE: the actual insertion happens inside the `value` setter below, not in
		// `.callback`. When the option list is long, ComfyUI renders a searchable
		// "Filter list" overlay (see docs/yoshiaki/tasks_done.md) that only ever sets
		// `widget.value = picked` on selection -- it does not also invoke
		// `widget.callback`. The setter is the one path guaranteed to fire regardless
		// of which combo UI ComfyUI decides to render, so all the logic lives there.
		node._wildcard_value = WILDCARD_LABEL;

		Object.defineProperty(wildcard_widget, "value", {
			set: (value) => {
				if (value === WILDCARD_LABEL) return;
				node._wildcard_value = value;
				if (wildcard_text_widget.value !== '') {
					wildcard_text_widget.value += ', ';
				}
				wildcard_text_widget.value += value;
			},
			get: () => WILDCARD_LABEL
		});

		Object.defineProperty(wildcard_widget.options, "values", {
			set: () => {},
			get: () => items_in_folder(wildcards_list, wildcard_entry_path, node._wildcard_folder)
		});

		wildcard_widget.serializeValue = () => WILDCARD_LABEL;

		// --- LoRA combo (YoshiakiWildcardEncode only), filtered by folder ---
		if (has_lora) {
			node._lora_value = LORA_LABEL;

			Object.defineProperty(lora_widget, "value", {
				set: (value) => {
					if (value === LORA_LABEL) return;
					node._lora_value = value;
					let lora_name = value;
					if (lora_name.endsWith('.safetensors')) {
						lora_name = lora_name.slice(0, -12);
					}
					wildcard_text_widget.value += `<lora:${lora_name}>`;
				},
				get: () => LORA_LABEL
			});

			Object.defineProperty(lora_widget.options, "values", {
				set: () => {},
				get: () => items_in_folder(lora_list, lora_entry_path, node._lora_folder)
			});

			lora_widget.serializeValue = () => LORA_LABEL;
		}

		wildcard_text_widget.inputEl.placeholder = "Wildcard Prompt (User input)";
		populated_text_widget.inputEl.placeholder = "Populated Prompt (Will be generated automatically)";
		populated_text_widget.inputEl.disabled = true;

		Object.defineProperty(mode_widget, "value", {
			set: (value) => {
				node._mode_value = value;
				populated_text_widget.inputEl.disabled = node._mode_value === 'populate';
			},
			get: () => node._mode_value !== undefined ? node._mode_value : 'populate'
		});
	}
});
