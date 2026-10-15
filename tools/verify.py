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
    if args.runtime_only:
        suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=p.name)
            for p in sorted((ROOT/'tests').glob('test_*.py'))
            if p.name not in {'test_traceability.py','test_specframe.py'})
    else:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordedResult).run(suite)
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "skills/synframe").rglob("*"))
                                if p.is_file() and "__pycache__" not in p.parts},
              "test_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT / "tests").glob("*.py"))},
              "verification_tool_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT / "tools").glob("*.py"))},
              "duration_seconds": round(time.monotonic() - started, 3), "tests_run": result.testsRun,
              "passed": result.wasSuccessful(), "results": result.records,
              "scope": "deterministic schema, graph, transactions, invalidation, recovery, gate and CLI behavior; not autonomous host reasoning quality"}
    output = ROOT / "docs" / "verification" / "core-results.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
