"""Real verifier runs must bind evidence to the files actually exercised."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class VerificationEvidenceAcceptance(unittest.TestCase):
    def verify_mutation(self, target, *, create=False, runtime_only=True):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for directory in ['tools','tests','skills/synframe']:
                (root/directory).mkdir(parents=True)
            shutil.copy2(ROOT/'tools/verify.py',root/'tools/verify.py')
            (root/'skills/synframe/SKILL.md').write_text('Exact synthetic fixture source')
            for relative in ['tests/test_specframe.py','tests/test_specframe_host.py',
                             'tools/check_specframe.py','tools/install_specframe.py',
                             'tools/check_specframe_host.py','tools/install_specframe_host.py']:
                (root/relative).write_text('# unrelated synthetic skill file\n')
            script=("import unittest\nfrom pathlib import Path\n"
                    "class Probe(unittest.TestCase):\n"
                    " def test_changes_during_run(self):\n"
                    f"  p=Path(__file__).resolve().parents[1]/{target!r}\n"
                    + ("  p.write_text('# actual in-run addition\\n')\n" if create else
                       "  p.write_text(p.read_text()+'\\n# actual in-run change\\n')\n"))
            (root/'tests/test_probe.py').write_text(script)
            result=subprocess.run([sys.executable,str(root/'tools/verify.py')]+(['--runtime-only'] if runtime_only else []),
                                  text=True,capture_output=True)
            report=json.loads((root/'docs/verification/core-results.json').read_text())
            self.assertTrue(report['tests_passed'])
            self.assertEqual(report['tests_run'],1)
            return result,report

    def test_relevant_source_test_and_verifier_changes_cannot_certify_the_end_version(self):
        for target,create in [('skills/synframe/SKILL.md',False),('tests/test_probe.py',False),
                              ('tools/verify.py',False),('tools/check_synframe_host.py',True),
                              ('tests/test_synframe_added.py',True)]:
            with self.subTest(target=target):
                result,report=self.verify_mutation(target,create=create)
                self.assertEqual(result.returncode,1)
                self.assertFalse(report['passed'])
                self.assertFalse(report['evidence_identity_stable'])
                self.assertNotEqual(report['identity_before'],
                    {name:report[name] for name in report['identity_before']})

    def test_other_skill_changes_during_runtime_checks_do_not_invalidate_their_identity(self):
        for target,create in [('tests/test_specframe.py',False),('tests/test_specframe_host.py',False),
                ('tools/check_specframe.py',False),('tools/install_specframe.py',False),
                ('tools/check_specframe_host.py',False),('tools/install_specframe_host.py',False),
                ('tools/check_specframe_added.py',True),('tests/test_specframe_added.py',True)]:
            with self.subTest(target=target):
                result,report=self.verify_mutation(target,create=create)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(report['passed'])
                self.assertTrue(report['evidence_identity_stable'])
                self.assertNotIn(target,report['test_hashes'])
                self.assertNotIn(target,report['verification_tool_hashes'])
        result,report=self.verify_mutation('tools/check_specframe_host.py',runtime_only=False)
        self.assertEqual(result.returncode,1)
        self.assertFalse(report['passed'])
        self.assertFalse(report['evidence_identity_stable'])
        self.assertIn('tools/check_specframe_host.py',report['verification_tool_hashes'])


if __name__=='__main__':
    unittest.main()
