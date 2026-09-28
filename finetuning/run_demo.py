"""Run the trained adapter through the existing source/policy/audit gates."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'part2'))
from ingestion import resolve_files
from run_mvp import print_packet
from approval import prompt_for_decision
from mlx_client import MLXClient

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--invoice',required=True)
    p.add_argument('--email')
    p.add_argument('--base',action='store_true')
    p.add_argument('--extractor',choices=['ladder','lfm'],default='ladder',
                   help='ladder (default): rules first, LFM only when rules cannot finish; lfm: always use the model')
    p.add_argument('--review',action='store_true',
                   help="Prompt for the reviewer's decision and record it in the audit log")
    p.add_argument('--no-injection-screen',action='store_true',
                   help='Red-team only: skip the phrase tripwire so the document reaches the model')
    args=p.parse_args()
    print('Rules or local LFM extraction -> Python validation and lookups -> human approval')
    client=MLXClient(ROOT/'models/LFM2.5-2.6B-MLX/4bit',
                     None if args.base else ROOT/'adapters/invoice',lazy=True)
    packet=resolve_files(args.invoice,args.email,client=client,
                       injection_screen=not args.no_injection_screen,extractor=args.extractor)
    print_packet(packet, verbose=True)
    if args.review:
        prompt_for_decision(packet)
    if packet['disposition']['exception_type'] in ('input_failure','extraction_failure','backend_failure','audit_failure'):
        raise SystemExit(2)
