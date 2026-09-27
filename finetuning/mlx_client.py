"""Local MLX bridge to the existing extraction-only chat client contract."""
import ast
import json
import re
from types import SimpleNamespace as NS


def parse_native_call(text):
    # Never execute model code. Accept exactly one literal keyword-only call.
    final = text.rsplit('</think>', 1)[-1].strip()
    match = re.fullmatch(r'<\|tool_call_start\|>\s*(\[.*\])\s*<\|tool_call_end\|>', final, re.S)
    if not match:
        raise ValueError('Expected one native LFM tool-call block')
    tree = ast.parse(match[1], mode='eval').body
    if not isinstance(tree, ast.List) or len(tree.elts) != 1:
        raise ValueError('Expected exactly one tool call')
    call = tree.elts[0]
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or call.func.id != 'submit_extracted_fields' or call.args):
        raise ValueError('Unexpected tool or positional arguments')
    fields = {}
    for kw in call.keywords:
        if kw.arg is None or kw.arg in fields:
            raise ValueError('Duplicate or expanded tool arguments')
        fields[kw.arg] = ast.literal_eval(kw.value)
    return fields


class MLXClient:
    def __init__(self, model_path, adapter_path=None, max_tokens=1200):
        from mlx_lm import load
        self.model, self.tokenizer = load(str(model_path), adapter_path=str(adapter_path) if adapter_path else None)
        self.max_tokens = max_tokens
        self.chat = NS(completions=self)
        self.last = {}

    def create(self, *, messages, tools=None, **kwargs):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        self.last = {}
        if not tools:
            raise ValueError('MLX bridge is extraction-only; use generate_brief=False')
        prompt = self.tokenizer.apply_chat_template(messages, tools=tools,
                    add_generation_prompt=True, tokenize=False)
        text, last = '', None
        for chunk in stream_generate(self.model, self.tokenizer, prompt=prompt,
                max_tokens=self.max_tokens, sampler=make_sampler(temp=0.0)):
            text += chunk.text
            last = chunk
        self.last = {'text': text, 'generation_tokens': last.generation_tokens if last else 0,
                     'peak_memory_gb': last.peak_memory if last else None,
                     'finish_reason': last.finish_reason if last else 'empty'}
        calls = []
        try:
            fields = parse_native_call(text)
            calls = [NS(function=NS(name='submit_extracted_fields', arguments=json.dumps(fields)))]
        except (ValueError, SyntaxError, TypeError) as exc:
            # Return an invalid response to the existing bounded repair loop.
            # Generation/transport errors still propagate as operational failures.
            self.last['parse_error'] = str(exc)
        return NS(choices=[NS(finish_reason='length' if last and last.finish_reason == 'length' else 'tool_calls',
                              message=NS(tool_calls=calls, content=None))],
                  usage=NS(completion_tokens=last.generation_tokens if last else 0))
