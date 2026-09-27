"""Frozen, first-attempt paired evaluation; no test-driven checkpoint selection."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'part2'))
import agent
from backends import money, lookup_purchase_order, lookup_vendor, compute_mismatch
from validation import FIELDS, validate_extraction
from mlx_client import MLXClient


def exact(actual, gold):
    try:
        fields = all(money(actual[k]) == money(gold[k]) if k == 'invoice_amount'
                     else actual[k] == gold[k] for k in FIELDS)
        items = len(actual['line_items']) == len(gold['line_items']) and all(
            a['description'] == b['description'] and money(a['amount']) == money(b['amount'])
            for a,b in zip(actual['line_items'], gold['line_items']))
        return fields, fields and items
    except (KeyError, TypeError, ValueError):
        return False, False


def route(fields):
    po = lookup_purchase_order(fields['po_number'])
    vendor = lookup_vendor(fields['vendor_name'])
    mismatch = compute_mismatch(fields, po, vendor)
    d = agent.decide_disposition(fields, po, vendor, mismatch, [])
    return d['exception_type'], d['recommended_action']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', default=str(ROOT/'models/LFM2.5-2.6B-MLX/4bit'))
    p.add_argument('--adapter')
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args()
    if args.output.exists():
        p.error('Choose a new output path; recorded evidence is not overwritten')
    manifest=json.loads((ROOT/'data/manifest.json').read_text())
    for name,meta in manifest['files'].items():
        assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==meta['sha256']
    client=MLXClient(args.model,args.adapter)
    cases=[json.loads(x) for x in (ROOT/'data/test_cases.jsonl').read_text().splitlines()]
    report={'method':'lora' if args.adapter else 'base', 'model':args.model,
            'revision':'b41f2b65685e95418f1ac809bb022d4f79e1ab27', 'platform':platform.platform(),
            'adapter_sha256':hashlib.sha256((Path(args.adapter)/'adapters.safetensors').read_bytes()).hexdigest() if args.adapter else None,
            'test_sha256':manifest['files']['test_cases.jsonl']['sha256'],
            'protocol':{'temperature':0,'max_tokens':1200,'attempts':1,'brief':False,
                        'scope':'synthetic held-out extraction and downstream mock policy; no OCR'},'rows':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for case in cases:
        start=time.monotonic()
        row={'id':case['id'],'fields_exact':False,'all_exact':False,'validated':False,
             'route_correct':False,'proposal':False,'incorrect_proposal':False}
        try:
            result=client.create(messages=agent.extraction_messages(case['invoice'],case['email']),tools=[agent.EXTRACT_TOOL])
            fields=agent.parse_json_object(result.choices[0].message.tool_calls[0].function.arguments)
            row['fields_exact'],row['all_exact']=exact(fields,case['gold'])
            errors=validate_extraction(fields,case['invoice'],case['email'])
            if result.choices[0].finish_reason=='length': errors.append('truncated output')
            row['validation_errors']=errors
            row['validated']=not errors
            if not errors:
                got,expected=route(fields),route(copy.deepcopy(case['gold']))
                row['route']=got
                row['route_correct']=got==expected
                row['proposal']=got[1] in ('short_pay','approve_match')
                row['incorrect_proposal']=row['proposal'] and (not row['all_exact'] or not row['route_correct'])
        except Exception as exc:
            row['error']=f'{type(exc).__name__}: {exc}'
        row.update(seconds=round(time.monotonic()-start,3), **client.last)
        report['rows'].append(row)
        rows=report['rows']
        report['summary']={k:sum(r[k] for r in rows) for k in ['fields_exact','all_exact','validated','route_correct','proposal','incorrect_proposal']}
        report['summary'].update(documents=len(rows),median_seconds=round(statistics.median(r['seconds'] for r in rows),3))
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        print(case['id'],row['all_exact'],row['validated'],row['seconds'],flush=True)
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__': main()
