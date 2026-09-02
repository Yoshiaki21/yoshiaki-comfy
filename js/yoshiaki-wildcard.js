import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Trimmed from ComfyUI-Impact-Pack's js/impact-pack.js: only the wildcard
// combo box + LoRA combo box + mode-widget behavior needed for
// YoshiakiWildcardProcessor / YoshiakiWildcardEncode.

let wildcards_list = [];

const WILDCARD_LABEL = "Select the Wildcard to add to the text";
const LORA_LABEL = "Select the LoRA to add to the text";

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
		const tbox_id = 0;
		// Encode widgets: wildcard_text(0), populated_text(1), mode(2), LoRA-select(3), Wildcard-select(4), seed(5)
		// Processor widgets: wildcard_text(0), populated_text(1), mode(2), seed(3), [seed control](4), Wildcard-select(5)
		const wildcard_combo_id = has_lora ? 4 : 5;
		const lora_combo_id = 3;

		node._wildcard_value = WILDCARD_LABEL;

		const wildcard_widget = node.widgets[wildcard_combo_id];
		wildcard_widget.callback = (value) => {
			if (value === WILDCARD_LABEL) return;
			if (node.widgets[tbox_id].value !== '') {
				node.widgets[tbox_id].value += ', ';
			}
			node.widgets[tbox_id].value += value;
		};

		Object.defineProperty(wildcard_widget, "value", {
			set: (value) => {
				if (value !== WILDCARD_LABEL) node._wildcard_value = value;
			},
			get: () => WILDCARD_LABEL
		});

		Object.defineProperty(wildcard_widget.options, "values", {
			set: () => {},
			get: () => wildcards_list
		});

		wildcard_widget.serializeValue = () => WILDCARD_LABEL;

		if (has_lora) {
			node._lora_value = LORA_LABEL;
			const lora_widget = node.widgets[lora_combo_id];

			lora_widget.callback = (value) => {
				if (value === LORA_LABEL) return;
				let lora_name = value;
				if (lora_name.endsWith('.safetensors')) {
					lora_name = lora_name.slice(0, -12);
				}
				node.widgets[tbox_id].value += `<lora:${lora_name}>`;
			};

			Object.defineProperty(lora_widget, "value", {
				set: (value) => {
					if (value !== LORA_LABEL) node._lora_value = value;
				},
				get: () => LORA_LABEL
			});

			lora_widget.serializeValue = () => LORA_LABEL;
		}

		node.widgets[0].inputEl.placeholder = "Wildcard Prompt (User input)";
		node.widgets[1].inputEl.placeholder = "Populated Prompt (Will be generated automatically)";
		node.widgets[1].inputEl.disabled = true;

		const populated_text_widget = node.widgets.find(w => w.name === 'populated_text');
		const mode_widget = node.widgets.find(w => w.name === 'mode');

		Object.defineProperty(mode_widget, "value", {
			set: (value) => {
				node._mode_value = value;
				populated_text_widget.inputEl.disabled = node._mode_value === 'populate';
			},
			get: () => node._mode_value !== undefined ? node._mode_value : 'populate'
		});
	}
});
