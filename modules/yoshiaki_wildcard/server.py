"""
Server routes + on-prompt hook for the wildcard nodes.

Trimmed from ComfyUI-Impact-Pack's `impact/impact_server.py`: only the
bits YoshiakiWildcardProcessor / YoshiakiWildcardEncode actually need
(wildcard listing/refresh for the frontend combo box, and the
'populate' mode auto-resolution before a prompt is queued). None of the
SAM / detector / preview-bridge server code is pulled in.
"""

import logging

from server import PromptServer

from . import wildcards


@PromptServer.instance.routes.get("/yoshiaki/wildcards/list")
async def wildcards_list(request):
    from aiohttp import web
    return web.json_response({"data": wildcards.get_wildcard_list()})


@PromptServer.instance.routes.get("/yoshiaki/wildcards/refresh")
async def wildcards_refresh(request):
    from aiohttp import web
    wildcards.wildcard_load()
    return web.json_response({"data": wildcards.get_wildcard_list()})


def find_input_value(input_node, prompt, input_type=int, input_keys=('value',)):
    input_val = None

    try:
        for n in input_keys:
            input_val = input_node['inputs'].get(n, None)
            if isinstance(input_val, input_type):
                break
            elif isinstance(input_val, list) and len(input_val):
                input_val = find_input_value(prompt[input_val[0]], prompt=prompt, input_type=input_type, input_keys=input_keys)
                if input_val is not None:
                    break
    except Exception as e:
        logging.warning(f"[yoshiaki-comfy] Error encountered on find {input_type} value - {e}")

    return input_val


def onprompt_populate_wildcards(json_data):
    prompt = json_data['prompt']

    updated_widget_values = {}
    for k, v in prompt.items():
        if 'class_type' in v and (v['class_type'] == 'YoshiakiWildcardEncode' or v['class_type'] == 'YoshiakiWildcardProcessor'):
            inputs = v['inputs']

            if inputs['mode'] == 'populate' and isinstance(inputs['populated_text'], str):
                if isinstance(inputs['seed'], list):
                    try:
                        input_node = prompt[inputs['seed'][0]]
                        if input_node['class_type'] == 'Seed (rgthree)':
                            input_seed = int(input_node['inputs']['seed'])
                            if not isinstance(input_seed, int):
                                continue
                        else:
                            input_seed = find_input_value(input_node, prompt=prompt, input_type=int, input_keys=('int', 'seed', 'value'))
                            if input_seed is None:
                                logging.info(f"[yoshiaki-comfy] Only `Seed (rgthree)` and `Primitive` nodes are allowed as the seed for '{v['class_type']}'. It will be ignored.")
                                continue
                    except Exception:
                        continue
                else:
                    input_seed = int(inputs['seed'])

                inputs['populated_text'] = wildcards.process(inputs['wildcard_text'], input_seed)
                inputs['mode'] = 'reproduce'

                PromptServer.instance.send_sync("yoshiaki-node-feedback", {"node_id": k, "widget_name": "populated_text", "type": "STRING", "value": inputs['populated_text']})
                updated_widget_values[k] = inputs['populated_text']

            if inputs['mode'] == 'reproduce':
                PromptServer.instance.send_sync("yoshiaki-node-feedback", {"node_id": k, "widget_name": "mode", "type": "STRING", "value": 'populate'})

    match json_data:
        case {"extra_data": {"extra_pnginfo": {"workflow": {"nodes": nodes}}}}:
            for node in nodes:
                match node:
                    case {"id": id, "widgets_values": widgets_values}:
                        key = str(id)
                        if key in updated_widget_values:
                            widgets_values[1] = updated_widget_values[key]
                            widgets_values[2] = "reproduce"


def onprompt(json_data):
    try:
        onprompt_populate_wildcards(json_data)
    except Exception:
        logging.exception("[yoshiaki-comfy] Error on prompt - wildcard auto-populate will not work.")

    return json_data


PromptServer.instance.add_on_prompt_handler(onprompt)

wildcards.wildcard_load()
