import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Trimmed from ComfyUI-Impact-Pack's js/impact-pack.js: only the wildcard
// combo box + LoRA combo box + mode-widget behavior needed for
// YoshiakiWildcardProcessor / YoshiakiWildcardEncode, plus a folder filter
// for the wildcard combo (added later -- see docs/yoshiaki/tasks_done.md).

let wildcards_list = [];

const WILDCARD_LABEL = "Select the Wildcard to add to the text";
const LORA_LABEL = "Select the LoRA to add to the text";
const NO_FOLDER_LABEL = "(no folder)";
const FOLDER_STORAGE_PREFIX = "yoshiaki-wildcard-folder:";

async function load_wildcards() {
	try {
		let res = await api.fetchApi('/yoshiaki/wildcards/list');
		let data = await res.json();
		wildcards_list = data.data;
	} catch (error) {
		console.error('[yoshiaki-comfy] Failed to load wildcard list:', error);
	}
}

load_wildcards();

// entry looks like "__folder/sub/name__" (or "__name__" with no folder).
function wildcard_entry_parts(entry) {
	return entry.slice(2, -2).split('/');
}

// All folder paths that appear anywhere in wildcards_list, at every nesting
// level, flattened -- e.g. "a/b/c" contributes both "a" and "a/b".
function get_wildcard_folders() {
	const folders = new Set();
	for (const entry of wildcards_list) {
		const parts = wildcard_entry_parts(entry);
		for (let i = 1; i < parts.length; i++) {
			folders.add(parts.slice(0, i).join('/'));
		}
	}
	return [NO_FOLDER_LABEL, ...Array.from(folders).sort()];
}

// Wildcards whose immediate parent folder is exactly `folder`
// (NO_FOLDER_LABEL => wildcards directly under the wildcards root, no
// subfolders included).
function get_wildcards_in_folder(folder) {
	return wildcards_list.filter(entry => {
		const parts = wildcard_entry_parts(entry);
		const parent = parts.slice(0, -1).join('/');
		return folder === NO_FOLDER_LABEL ? parent === '' : parent === folder;
	});
}

// The first folder (in get_wildcard_folders() order) that actually has at
// least one wildcard directly under it. Falls back to NO_FOLDER_LABEL if
// nothing has any entries at all (e.g. a brand-new empty wildcards/ dir).
function get_default_folder() {
	for (const folder of get_wildcard_folders()) {
		if (get_wildcards_in_folder(folder).length > 0) return folder;
	}
	return NO_FOLDER_LABEL;
}

function load_stored_folder(node) {
	try {
		return localStorage.getItem(FOLDER_STORAGE_PREFIX + node.id);
	} catch (error) {
		return null;
	}
}

function save_stored_folder(node, folder) {
	try {
		localStorage.setItem(FOLDER_STORAGE_PREFIX + node.id, folder);
	} catch (error) {
		// localStorage unavailable (private browsing, etc.) -- selection just won't persist.
	}
}

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
				await api.fetchApi('/yoshiaki/wildcards/refresh');
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

		// --- folder filter, inserted directly above the wildcard combo ---
		const stored_folder = load_stored_folder(node);
		const stored_folder_has_entries = stored_folder && get_wildcards_in_folder(stored_folder).length > 0;
		node._wildcard_folder = stored_folder_has_entries ? stored_folder : get_default_folder();

		const folder_widget = node.addWidget(
			'combo',
			'Wildcard Folder',
			node._wildcard_folder,
			(value) => {
				node._wildcard_folder = value;
				save_stored_folder(node, value);
			},
			{ values: get_wildcard_folders() }
		);
		Object.defineProperty(folder_widget.options, "values", {
			set: () => {},
			get: () => get_wildcard_folders()
		});
		// Move it from the end of the widget list to directly above the wildcard combo.
		const insert_before_idx = node.widgets.indexOf(wildcard_widget);
		node.widgets.pop();
		node.widgets.splice(insert_before_idx, 0, folder_widget);
		node.setSize(node.computeSize());

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
			get: () => get_wildcards_in_folder(node._wildcard_folder)
		});

		wildcard_widget.serializeValue = () => WILDCARD_LABEL;

		// --- LoRA combo (YoshiakiWildcardEncode only) ---
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
