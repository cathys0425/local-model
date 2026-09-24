"""Observe local request outcomes while running the existing CLI."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'part2'))
import agent
import run_mvp
client = agent._client()
def create(**kwargs):
    started = time.monotonic()
    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    print('LOCAL REQUEST:', 'extract' if kwargs.get('tools') else 'brief',
          'seconds=', round(time.monotonic()-started, 2), 'finish=', choice.finish_reason,
          'tokens=', response.usage.completion_tokens,
          'tools=',len(choice.message.tool_calls or []),
          'content_chars=',len(choice.message.content or ''),flush=True)
    if choice.message.tool_calls:
        print('TOOL ARGUMENTS:', choice.message.tool_calls[0].function.arguments,flush=True)
    return response
agent._client = lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
raise SystemExit(run_mvp.main())
