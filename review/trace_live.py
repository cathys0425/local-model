"""Run unchanged pipeline, recording local model responses for review."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'part2'))
import agent
client=agent._client()
responses=[]
def create(**kwargs):
    start=time.monotonic()
    try:
        response=client.chat.completions.create(**kwargs)
        responses.append({'phase':'extraction' if 'tools' in kwargs else 'brief','seconds':round(time.monotonic()-start,2),'response':response.model_dump()})
        return response
    except Exception as exc:
        responses.append({'phase':'extraction' if 'tools' in kwargs else 'brief','seconds':round(time.monotonic()-start,2),'error':repr(exc)})
        raise
wrapped=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
packet=agent.resolve_invoice(agent.load_invoice(ROOT/'part2/artifacts/invoice_001.txt'),client=wrapped,generate_brief=True)
(ROOT/'review/live-model-trace.json').write_text(json.dumps({'responses':responses,'packet':packet},indent=2))
for item in responses:
    print(json.dumps(item))
print('FINAL BRIEF:',packet['clerk_brief'])
