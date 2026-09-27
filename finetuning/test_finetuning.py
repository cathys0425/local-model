"""Offline checks for experiment separation and untrusted native-call parsing."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent/'part2'))
from mlx_client import parse_native_call
from prepare_data import examples
from validation import validate_extraction


class FineTuningTests(unittest.TestCase):
    def test_split_identities_and_vendors_do_not_overlap(self):
        splits=[list(examples(s,n)) for s,n in [('train',96),('valid',16),('test',24)]]
        for key in ['vendor','layout_family']:
            sets=[{r[key] for r in rows} for rows in splits]
            for i in range(3):
                for j in range(i): self.assertFalse(sets[i]&sets[j])
        for key in ['invoice_number','po_number']:
            sets=[{r['gold'][key] for r in rows} for rows in splits]
            for i in range(3):
                for j in range(i): self.assertFalse(sets[i]&sets[j])

    def test_all_gold_passes_existing_source_checks(self):
        for split,n in [('train',96),('valid',16),('test',24)]:
            for case in examples(split,n):
                self.assertEqual(validate_extraction(copy.deepcopy(case['gold']),case['invoice'],case['email']),[])

    def test_native_call_parser_accepts_literals(self):
        text="reasoning</think><|tool_call_start|>[submit_extracted_fields(po_number='PO-1', line_items=[])]<|tool_call_end|>"
        self.assertEqual(parse_native_call(text),{'po_number':'PO-1','line_items':[]})

    def test_native_parser_rejects_execution_multiple_and_duplicate_calls(self):
        for value in ["[other()]", "[submit_extracted_fields(), submit_extracted_fields()]",
                      "[submit_extracted_fields(x=__import__('os').getcwd())]",
                      "[submit_extracted_fields(**{})]", "[submit_extracted_fields(x=1,x=2)]"]:
            with self.assertRaises((ValueError,SyntaxError)):
                parse_native_call('<|tool_call_start|>'+value+'<|tool_call_end|>')


if __name__=='__main__': unittest.main()
