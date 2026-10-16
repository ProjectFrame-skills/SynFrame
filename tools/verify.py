"""Run meaningful core acceptance checks and persist the observed results."""

import json
import hashlib
import sys
import time
import unittest
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OTHER_SKILL_PREFIXES = ('test_specframe', 'check_specframe', 'install_specframe')


def evidence_identity(root, runtime_only):
    tests = [p for p in sorted((root / 'tests').glob('*.py'))
             if not runtime_only or (p.name != 'test_traceability.py'
                 and not p.name.startswith(OTHER_SKILL_PREFIXES))]
    tools = [p for p in sorted((root / 'tools').glob('*.py'))
             if not runtime_only or not p.name.startswith(OTHER_SKILL_PREFIXES)]
    groups = {'source_hashes':[p for p in sorted((root/'skills/synframe').rglob('*'))
                              if p.is_file() and '__pycache__' not in p.parts],
              'test_hashes':tests, 'verification_tool_hashes':tools}
    return {name:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            for name,paths in groups.items()}


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "FAIL", "reason": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"test": test.id(), "status": "ERROR", "reason": self._exc_info_to_string(err, test)})


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-only',action='store_true',help='SynFrame runtime checks, excluding local agreement governance and other skills')
    args=parser.parse_args()
    started = time.monotonic()
    identity_before = evidence_identity(ROOT, args.runtime_only)
    if args.runtime_only:
        suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=p.name)
            for p in sorted((ROOT/'tests').glob('test_*.py'))
            if p.name != 'test_traceability.py' and not p.name.startswith(OTHER_SKILL_PREFIXES))
    else:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordedResult).run(suite)
    identity_after = evidence_identity(ROOT, args.runtime_only)
    identity_stable = identity_before == identity_after
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "evidence_scope": "synframe-runtime" if args.runtime_only else "workspace",
              **identity_after, "identity_before":identity_before,
              "evidence_identity_stable":identity_stable,
              "duration_seconds": round(time.monotonic() - started, 3), "tests_run": result.testsRun,
              "tests_passed": result.wasSuccessful(), "passed": result.wasSuccessful() and identity_stable,
              "results": result.records,
              "scope": "deterministic schema, graph, transactions, invalidation, recovery, gate and CLI behavior; not autonomous host reasoning quality"}
    output = ROOT / "docs" / "verification" / "core-results.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    sys.exit(0 if report['passed'] else 1)
