"""Offline checks for recording a reviewer's decision against an audited packet."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent
import approval
import run_mvp


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.audit_dir = Path(folder.name)
        patcher = patch.object(agent, 'AUDIT_DIR', self.audit_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def packet(self, case):
        text = run_mvp.CASES[case]['file'].read_text()
        return agent.resolve_invoice(text, extractor='rules')

    def decisions(self):
        path = self.audit_dir / 'decisions.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_approval_records_the_proposed_amount_not_the_invoice_amount(self):
        packet = self.packet('amount_mismatch')
        record = approval.record_decision(packet['packet_id'], 'approve', 'Dana Reviewer', 'backup received')
        self.assertEqual(record['approved_amount_usd'], '12000.00')
        self.assertEqual(record['vendor_id'], 'V-100')
        self.assertFalse(record['payment_posted'])
        self.assertEqual(self.decisions(), [record])

    def test_review_packets_cannot_be_approved(self):
        packet = self.packet('unknown_po')
        self.assertEqual(packet['human_decision'], ['reject', 'escalate'])
        with self.assertRaisesRegex(ValueError, 'not available'):
            approval.record_decision(packet['packet_id'], 'approve', 'Dana Reviewer')
        record = approval.record_decision(packet['packet_id'], 'escalate', 'Dana Reviewer')
        self.assertIsNone(record['approved_amount_usd'])

    def test_one_decision_per_packet_and_only_for_audited_packets(self):
        packet = self.packet('matched')
        approval.record_decision(packet['packet_id'], 'approve', 'Dana Reviewer')
        with self.assertRaisesRegex(ValueError, 'already has a recorded decision'):
            approval.record_decision(packet['packet_id'], 'reject', 'Dana Reviewer')
        with self.assertRaisesRegex(ValueError, 'no audited packet'):
            approval.record_decision('not-a-packet', 'reject', 'Dana Reviewer')
        with self.assertRaisesRegex(ValueError, 'reviewer name'):
            approval.record_decision(self.packet('matched')['packet_id'], 'reject', ' ')

    def test_interactive_prompt_records_or_skips(self):
        packet = self.packet('matched')
        answers = iter(['skip'])
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(approval.prompt_for_decision(packet, ask=lambda _: next(answers)))
        answers = iter(['approve', 'Dana Reviewer', ''])
        with redirect_stdout(io.StringIO()) as out:
            record = approval.prompt_for_decision(packet, ask=lambda _: next(answers))
        self.assertEqual(record['approved_amount_usd'], '12000.00')
        self.assertIn('payment posted: no', out.getvalue())

    def test_failed_audit_cannot_be_decided(self):
        with patch.object(agent, 'write_audit', side_effect=OSError('disk full')):
            packet = self.packet('matched')
        self.assertEqual(packet['human_decision'], ['reject', 'escalate'])
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(approval.prompt_for_decision(packet, ask=lambda _: 'approve'))
        self.assertEqual(self.decisions(), [])


if __name__ == '__main__':
    unittest.main()
