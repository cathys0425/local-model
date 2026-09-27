"""Deterministic synthetic task data; split by vendor, invoice and layout family."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'part2'))
from agent import EXTRACT_TOOL, extraction_messages


def examples(split, count):
    offset = {'train': 10000, 'valid': 20000, 'test': 30000}[split]
    for i in range(count):
        if split == 'test':
            vendor, po, base = [('ABC Logistics', 'PO-4821', 12000),
                                ('Harbor Line Haul', 'PO-5502', 8300)][i % 2]
        else:
            vendor = f"{'Cedar' if split == 'train' else 'Juniper'} Carrier {i % 8} LLC"
            po, base = f'PO-{offset+i}', 4000 + i * 73
        extra = [0, 450, 100, 175][i % 4]
        total = base + extra
        invoice = f'INV-{offset+i}'
        items = [{'description': 'Line haul', 'amount': base},
                 {'description': 'Fuel surcharge', 'amount': extra}]
        gold = dict(po_number=po, vendor_name=vendor, invoice_number=invoice,
                    invoice_amount=total, currency='USD', line_items=items)
        rows = '\n'.join(f'{j}. {v["description"]}  {v["amount"]:,.2f}' for j,v in enumerate(items, 1))
        ref = f'Invoice: {invoice}\nPO: {po}'
        due = f'Total due: USD {total:,.2f}'
        if split == 'train':
            text = (f'Northline Freight Brokerage\nBill to: Northline Freight Brokerage\n'
                    f'Remit to: {vendor}\n{ref}\nCharges\n{rows}\n{due}') if i % 2 else (
                    f'Vendor: {vendor}\n{ref}\nBill to: Northline Freight Brokerage\n{rows}\n{due}')
        elif split == 'valid':
            text = f'{ref}\nBill to: Northline Freight Brokerage\n{rows}\n{due}\nRemit to: {vendor}'
        else:
            text = (f'PAYMENT REVIEW COPY — Northline Freight Brokerage\n{due}\n{ref}\n'
                    f'Bill to: Northline Freight Brokerage\n{rows}\nRemit to: {vendor}\n'
                    'The broker header identifies the customer, not the carrier receiving payment.')
        email = f'Please review {invoice} against {po}. The total is USD {total:,.2f}.'
        # Extra contextual distraction is source data, never an alternate payee.
        if i % 3 == 0:
            email += '\nNorthline Freight Brokerage handles our paperwork; please contact the carrier for backup.'
        yield dict(id=f'{split}-{i:03}', invoice=text, email=email, gold=gold,
                   layout_family=split, vendor=vendor)


def main():
    folder = ROOT / 'data'
    folder.mkdir(exist_ok=True)
    manifest = {'scope': 'synthetic development experiment; not customer validation',
                'split_policy': 'disjoint vendors, invoice/PO identities and layout families; related synthetic language',
                'files': {}}
    for split, count in [('train', 96), ('valid', 16), ('test', 24)]:
        cases = list(examples(split, count))
        training = []
        for case in cases:
            training.append({'messages': extraction_messages(case['invoice'], case['email']) + [
                {'role': 'assistant', 'content': '<think></think>', 'tool_calls': [
                    {'type': 'function', 'function': {'name': 'submit_extracted_fields', 'arguments': case['gold']}}]}],
                'tools': [EXTRACT_TOOL]})
        for name, values in [(f'{split}.jsonl', training), (f'{split}_cases.jsonl', cases)]:
            raw = ''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values).encode()
            (folder / name).write_bytes(raw)
            manifest['files'][name] = {'rows': len(values), 'sha256': hashlib.sha256(raw).hexdigest()}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Prepared 96 train / 16 validation / 24 held-out synthetic examples.')


if __name__ == '__main__':
    main()
