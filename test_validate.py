# SPDX-License-Identifier: Apache-2.0
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import validate

CASE=Path(__file__).parent/"examples/q8-scale-registers"

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((CASE/"plan.json").read_text())
        with (CASE/"timings.csv").open(newline="") as f:self.rows=list(csv.DictReader(f))

    def test_historical_case_does_not_promote_local_gain(self):
        report=validate.analyze(CASE)
        self.assertEqual(report["local"]["records"],504)
        self.assertTrue(report["local"]["local_screen_positive"])
        self.assertFalse(report["service"]["C1"]["all_candidates_above_both"])
        self.assertTrue(report["service"]["C4"]["all_candidates_above_both"])
        self.assertFalse(report["end_to_end_gain_confirmed"])
        self.assertAlmostEqual(report["local"]["groups"][0]["saved_vs_A0_pct"],2.756,places=3)

    def test_missing_duplicate_unexpected_and_nonfinite_rejected(self):
        for rows in (self.rows[:-1],self.rows+[self.rows[0]],self.rows+[dict(self.rows[0],rank="2")],
                     [dict(self.rows[0],ms="nan")]+self.rows[1:]):
            with self.subTest(rows=len(rows)),self.assertRaises(ValueError):
                validate.timing_report(rows,self.plan)

    def test_empty_plan_rejected(self):
        with self.assertRaises(ValueError):validate.timing_report([],dict(self.plan,ranks=[]))

    def test_negative_control_failure_rejected(self):
        records=json.loads((CASE/"checks.json").read_text())
        next(r for r in records if r.get("numeric"))["negative_tol"]=0
        with self.assertRaises(ValueError):validate.check_report(records,[0,1])

    def test_non_numeric_check_values_rejected(self):
        records=json.loads((CASE/"checks.json").read_text())
        for field in ("worst_tol","negative_tol","bitwise_repeats"):
            for value in ("not-a-number", None, [], {}, True, False):
                with self.subTest(field=field, value=value):
                    record=next(r for r in records if r.get("numeric"))
                    original=record[field]
                    record[field]=value
                    try:
                        with self.assertRaisesRegex(ValueError, field):
                            validate.check_report(records,[0,1])
                    finally:
                        record[field]=original

    def test_check_numeric_boundaries_rejected(self):
        records=json.loads((CASE/"checks.json").read_text())
        for field, values in (("worst_tol", (-0.1, 1.1, float("nan"), float("inf"))),
                              ("bitwise_repeats", (0, 1, 2.5, "2"))):
            for value in values:
                with self.subTest(field=field, value=value):
                    record=next(r for r in records if r.get("numeric"))
                    original=record[field]
                    record[field]=value
                    try:
                        with self.assertRaises(ValueError):
                            validate.check_report(records,[0,1])
                    finally:
                        record[field]=original

    def test_malformed_checks_cli_has_no_traceback_or_output(self):
        with tempfile.TemporaryDirectory() as root:
            case=Path(root)/"case"
            shutil.copytree(CASE, case)
            for field in ("worst_tol", "bitwise_repeats"):
                with self.subTest(field=field):
                    records=json.loads((CASE/"checks.json").read_text())
                    next(r for r in records if r.get("numeric"))[field]=None
                    (case/"checks.json").write_text(json.dumps(records), encoding="utf-8")
                    output=Path(root)/"result.json"
                    result=subprocess.run([sys.executable, str(Path(validate.__file__)),
                                           "analyze", str(case), "--output", str(output)],
                                          capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(field, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(output.exists())

    def test_interval_union_avoids_double_counting(self):
        self.assertEqual(validate.union_ms([(1,5),(3,7),(7,9)]),8)
        with (CASE.parent/"intervals.csv").open(newline="") as f:
            report=validate.attribution(list(csv.DictReader(f)))
        self.assertEqual(report["rounds"][0]["category_union_ms_per_token"]["moe"],3)

    def test_token_denominator_mismatch_rejected(self):
        rows=[dict(rank="0",request="x",round="1",actual_tokens=str(n),category="x",start_ms="0",end_ms="1") for n in (1,2)]
        with self.assertRaises(ValueError):validate.attribution(rows)

    def test_invalid_service_measurement_rejected(self):
        with self.assertRaises(ValueError):validate.service_report({"C1":{"A0":[1,2],"B":[3,4],"A1":[0,2]}})

if __name__=="__main__":unittest.main()
