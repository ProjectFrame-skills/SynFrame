"""Exact readonly transport fixtures, not claims about host understanding."""
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/synframe/scripts'))
from synframe_core.transport import read_contracts, encode_bundle
from synframe_host import read_contract


class ContractTransportAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'skill'
        (self.root/'references').mkdir(parents=True)
        self.texts = {'SKILL.md': '정확한 진입 계약\r\n끝\n',
                      'references/first.md': ('中文 한글 👩🏽‍💻 e\u0301 \\"quoted"\t\r\n'*1600),
                      'references/last.md': '마지막 조건\n' * 30}
        for name, text in self.texts.items():
            (self.root/name).write_bytes(text.encode('utf-8'))
        manifest = read_contract(self.root)
        self.request = {'ranges': [{'name': x['name'], 'sha256': x['sha256'],
                                    'offset': 0, 'end': x['characters']} for x in manifest['files']]}

    def tearDown(self):
        self.temp.cleanup()

    def check_budget(self, value, budget):
        actual = len(encode_bundle(value).encode('utf-8'))
        self.assertEqual(value['budget']['serialized_bytes'], actual)
        self.assertLessEqual(actual, budget)

    def test_multiple_files_roundtrip_every_exact_unicode_byte_with_bounded_continuation(self):
        request = copy.deepcopy(self.request)
        collected = {name: [] for name in self.texts}
        first = True
        while True:
            value = read_contracts(self.root, request, 4096)
            self.check_budget(value, 4096)
            self.assertTrue(value['ranges'])
            if first:
                self.assertFalse(value['complete'])
                first = False
            for chunk in value['ranges']:
                self.assertFalse(chunk['reused_retained'])
                expected = self.texts[chunk['name']][chunk['offset']:chunk['end']]
                self.assertEqual(chunk['text'], expected)
                self.assertEqual(chunk['chunk_sha256'], hashlib.sha256(expected.encode('utf-8')).hexdigest())
                collected[chunk['name']].append(chunk['text'])
            if value['complete']:
                self.assertEqual(value['remaining'], [])
                break
            self.assertNotEqual(request['ranges'], value['remaining'])
            request = {'ranges': value['remaining']}
        for name, chunks in collected.items():
            self.assertEqual(''.join(chunks).encode('utf-8'), (self.root/name).read_bytes())

    def test_complete_bundle_has_no_fixed_character_ceiling_and_respects_explicit_subranges(self):
        value = read_contracts(self.root, self.request, 1000000)
        self.assertTrue(value['complete'])
        self.assertGreater(max(len(x['text']) for x in value['ranges']), 6000)
        item = dict(self.request['ranges'][1], offset=17, end=9000)
        value = read_contracts(self.root, {'ranges': [item]}, 1000000)
        self.assertEqual(value['ranges'][0]['text'], self.texts[item['name']][17:9000])
        self.check_budget(value, 1000000)

    def test_changed_file_after_partial_read_rejects_continuation_without_refreshing_hash(self):
        value = read_contracts(self.root, self.request, 4096)
        name = value['remaining'][0]['name']
        (self.root/name).write_bytes(b'Actual changed contract')
        with self.assertRaisesRegex(ValueError, 'contract changed'):
            read_contracts(self.root, {'ranges': value['remaining']}, 4096)

    def test_explicit_retention_requires_current_identity_complete_coverage_and_actual_declaration(self):
        original = read_contracts(self.root, self.request, 1000000)
        retained = {'retained_in_current_context': True, 'ranges': original['ranges']}
        request = {**self.request, 'retained': retained}
        value = read_contracts(self.root, request, 4096)
        self.assertTrue(value['complete'])
        self.assertTrue(all(x['reused_retained'] and x['text'] == '' for x in value['ranges']))
        self.check_budget(value, 4096)
        lost = copy.deepcopy(request)
        lost['retained']['retained_in_current_context'] = False
        with self.assertRaisesRegex(ValueError, 'current context'):
            read_contracts(self.root, lost, 4096)
        bad = copy.deepcopy(request)
        bad['retained']['ranges'][0]['chunk_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'does not match'):
            read_contracts(self.root, bad, 4096)
        partial = copy.deepcopy(request)
        partial['retained']['ranges'] = retained['ranges'][:1]
        value = read_contracts(self.root, partial, 1000000)
        self.assertTrue(value['ranges'][0]['reused_retained'])
        self.assertEqual(value['ranges'][1]['text'], self.texts[value['ranges'][1]['name']])
        # An old receipt never suppresses the new file, even when declared retained.
        name = self.request['ranges'][0]['name']
        (self.root/name).write_bytes(b'new text')
        current = {'name': name, 'sha256': hashlib.sha256(b'new text').hexdigest(), 'offset': 0, 'end': 8}
        value = read_contracts(self.root, {'ranges': [current], 'retained': retained}, 4096)
        self.assertEqual(value['ranges'][0]['text'], 'new text')

    def test_invalid_ranges_and_small_budget_fail_instead_of_hiding_work_or_looping(self):
        item = self.request['ranges'][1]
        cases = [dict(item, name='../outside'), dict(item, offset=True), dict(item, end=item['end']+1),
                 dict(item, unknown='field'), dict(item, sha256='0'*64)]
        for spec in cases:
            with self.assertRaises(ValueError):
                read_contracts(self.root, {'ranges': [spec]}, 4096)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            read_contracts(self.root, {'ranges': [item, dict(item)]}, 4096)
        with self.assertRaisesRegex(ValueError, 'need at least'):
            read_contracts(self.root, self.request, 1)
        huge = {'ranges': [dict(item, offset=i, end=i+1) for i in range(1000)]}
        with self.assertRaisesRegex(ValueError, 'need at least'):
            read_contracts(self.root, huge, 4096)
        outside = Path(self.temp.name)/'outside.md'
        outside.write_text('not a bundled contract')
        link = self.root/'references/link.md'
        link.symlink_to(outside)
        spec = {'name': 'references/link.md', 'sha256': hashlib.sha256(outside.read_bytes()).hexdigest(),
                'offset': 0, 'end': len(outside.read_text())}
        with self.assertRaisesRegex(ValueError, 'outside skill directory'):
            read_contracts(self.root, {'ranges': [spec]}, 4096)

    def test_cli_emits_one_exact_bounded_json_and_never_creates_state(self):
        skill = ROOT/'skills/synframe'
        entries = read_contract(skill)['files']
        request = {'ranges': [{'name': x['name'], 'sha256': x['sha256'], 'offset': 0, 'end': x['characters']}
                              for x in entries if x['name'] in {'references/operating-contract.md', 'references/decision-loop.md'}]}
        state = Path(self.temp.name)/'must-not-exist'
        command = [sys.executable, str(skill/'scripts/synframe.py'), '--state', str(state),
                   'read-contracts', '--input', '-', '--max-bytes', '12000']
        result = subprocess.run(command, input=json.dumps(request).encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(result.stdout, encode_bundle(value).encode('utf-8'))
        self.assertEqual(len(result.stdout), value['budget']['serialized_bytes'])
        self.assertLessEqual(value['budget']['serialized_bytes'], 12000)
        self.assertFalse(state.exists())
        expected = read_contracts(skill, request, 12000)
        self.assertEqual(value, expected)

    def test_reported_minimum_budget_is_immediately_usable_including_its_own_digit_width(self):
        original = read_contracts(self.root, self.request, 1000000)
        retained = {'retained_in_current_context': True, 'ranges': original['ranges']}
        for request in [{'ranges': []}, self.request, {**self.request, 'retained': retained}]:
            with self.assertRaisesRegex(ValueError, r'need at least \d+ bytes') as caught:
                read_contracts(self.root, request, 1)
            minimum = int(re.search(r'need at least (\d+) bytes', str(caught.exception)).group(1))
            value = read_contracts(self.root, request, minimum)
            self.check_budget(value, minimum)
            self.assertTrue(value['complete'] or value['ranges'])


if __name__ == '__main__':
    unittest.main()
