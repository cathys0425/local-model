"""Run the trained adapter through the existing source/policy/audit gates."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'part2'))
from ingestion import resolve_files
from run_mvp import print_packet
from mlx_client import MLXClient

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--invoice',required=True)
    p.add_argument('--email')
    p.add_argument('--base',action='store_true')
    args=p.parse_args()
    client=MLXClient(ROOT/'models/LFM2.5-2.6B-MLX/4bit',
                     None if args.base else ROOT/'adapters/invoice')
    packet=resolve_files(args.invoice,args.email,client=client,generate_brief=False)
    print_packet(packet)
    if packet['disposition']['exception_type'] in ('input_failure','extraction_failure','backend_failure','audit_failure'):
        raise SystemExit(2)
