"""Synthetic first-generation routing/payload regressions. Never sends requests."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ptty-skill/scripts"))
import operation_catalog as catalog
import prepare_match_generation as generation
import workflow_state


def case():
    return {
        "mode": "platform", "event_id": "synthetic-event", "route_ssid": "synthetic-route",
        "project_ids": ["stage-a", "stage-b"],
        "plan": {"event_id": "synthetic-event", "complete": True, "project_ids": ["stage-a", "stage-b"]},
        "inventory": {"event_id": "synthetic-event", "complete": True,
                      "captured_at": "2030-01-01T09:00:00+08:00",
                      "matches": 0, "scheduled": 0, "started": 0, "results": 0},
        "draw_snapshot": {"binding": {"event_id": "synthetic-event"}, "complete": True,
                          "captured_at": "2030-01-01T09:00:00+08:00",
                          "rows": []},
        "sc_model_data": {"ZHSHOWMS": "SZ", "CCHGZ": "1", "ISLKZZH": "0", "FZFS": "ZZZPT"},
    }


class MatchGenerationTests(unittest.TestCase):
    def test_verified_empty_state_prepares_create_not_reset_or_redraw(self):
        request = case(); before = deepcopy(request)
        result = generation.prepare(request)
        self.assertEqual(request, before)
        self.assertEqual(result["request"]["headerData"],
                         {"ssid": "synthetic-route", "op": "scGl", "methodName": "czSc"})
        self.assertEqual(result["request"]["busData"], {
            "xmids": ["stage-a", "stage-b"], "type": "create", "scModelData": request["sc_model_data"]})
        self.assertEqual(result["draw_before_sha256"], workflow_state.fingerprint(request["draw_snapshot"]))
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["online_verified"])

    def test_existing_draw_and_zero_matches_require_complete_recheck(self):
        request = case()
        request["draw_snapshot"]["rows"] = [{"key": "stage-a/A/1", "values": {"entry_id": "entry-a"}}]
        with self.assertRaisesRegex(ValueError, "contradictory"):
            generation.prepare(request)

    def test_generation_catalog_resolves_to_plan_page_and_reset_remains_separate(self):
        data = catalog.load_catalog()
        op = catalog.resolve(data, "matches.generate")
        self.assertEqual((op["route"], op["component"], op["op"]), ("/trialGhIndex", "TrialGhIndex", "scGl"))
        self.assertIn("scGl/czSc (type=create)", op["methods"])
        self.assertNotIn("initScInfo", op["methods"])
        reset = catalog.resolve(data, "matches.reset")
        self.assertEqual(reset["route"], "/trialScGlIndex")
        self.assertIn("destructive_scope", reset["requires"])
        self.assertIn("destructive_scope", catalog.resolve(data, "plan.generate")["requires"])
        self.assertIn("matches.generate", {op["id"] for op in catalog.search(data, "已有签位")})

    def test_readonly_generation_still_blocked(self):
        op = catalog.resolve(catalog.load_catalog(), "matches.generate")
        result = catalog.preflight(catalog.load_catalog(), {"mode": "readonly", "operations": [op["id"]],
                                  "facts": {k: True for k in op["requires"]}})
        self.assertIn("outside_readonly_scope", result["steps"][0]["blocked_by"])

    def test_partial_or_existing_matches_never_prepared_as_first_generation(self):
        for field in ("matches", "scheduled", "started", "results"):
            for value in (1, None, "0", False, -1):
                with self.subTest(field=field, value=value):
                    request = case(); request["inventory"][field] = value
                    with self.assertRaises(ValueError): generation.prepare(request)

    def test_filtered_missing_or_cross_event_inventory_rejected(self):
        for field, value in (("complete", False), ("event_id", "another-event"), ("captured_at", None)):
            request = case(); request["inventory"][field] = value
            with self.assertRaises(ValueError): generation.prepare(request)

    def test_independent_and_file_only_modes_do_not_switch_to_platform(self):
        for mode in ("independent", "readonly", "file_only", None):
            request = case(); request["mode"] = mode
            with self.assertRaises(ValueError): generation.prepare(request)

    def test_wrong_or_incomplete_plan_and_missing_stages_rejected(self):
        for value in ([], ["stage-a", "stage-a"], ["unknown-stage"]):
            request = case(); request["project_ids"] = value
            with self.assertRaises(ValueError): generation.prepare(request)
        for key, value in (("complete", False), ("event_id", "another-event")):
            request = case(); request["plan"][key] = value
            with self.assertRaises(ValueError): generation.prepare(request)

    def test_draw_snapshot_complete_unique_and_bound_to_target(self):
        for key, value in (("complete", False), ("binding", {"event_id": "other"})):
            request = case(); request["draw_snapshot"][key] = value
            with self.assertRaises(ValueError): generation.prepare(request)
        request = case(); request["draw_snapshot"]["rows"] = [{"key": "same", "values": {}}] * 2
        with self.assertRaises(ValueError): generation.prepare(request)

    def test_missing_option_rejected_and_user_selected_options_preserved(self):
        request = case(); del request["sc_model_data"]["FZFS"]
        with self.assertRaises(ValueError): generation.prepare(request)
        request = case(); request["sc_model_data"] = {"ZHSHOWMS": "ZM", "CCHGZ": "6", "ISLKZZH": "1", "FZFS": "RSPT"}
        result = generation.prepare(request)
        self.assertEqual(result["request"]["busData"]["scModelData"], request["sc_model_data"])
        request["sc_model_data"]["CCHGZ"] = "unknown"
        with self.assertRaises(ValueError): generation.prepare(request)

    def test_recovery_rejects_changed_draw_after_generation_success(self):
        before = case()["draw_snapshot"]
        before["rows"] = [{"key": "stage-a/A/1", "values": {"member_ids": ["player-a"]}}]
        after = deepcopy(before)
        after["captured_at"] = "2030-01-01T09:02:00+08:00"
        after["rows"][0]["values"]["member_ids"] = ["player-other"]
        result = workflow_state.assess({"schema_version": 1, "operation_id": "matches.generate",
            "input_version": "synthetic-v1", "before": before, "desired": deepcopy(before), "current": after,
            "attempts": 1, "submitted_at": "2030-01-01T09:01:00+08:00",
            "evidence": {"session_valid": True, "contract_current": True, "transport": "success"}})
        self.assertEqual(result["status"], "conflict_review_required")
        self.assertEqual(result["retry_keys"], [])

    def test_cli_prepares_file_and_never_overwrites_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"; target = Path(directory) / "prepared.json"
            source.write_text(json.dumps(case()))
            cmd = [sys.executable, str(ROOT / "ptty-skill/scripts/prepare_match_generation.py"), str(source), "--out", str(target)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            prepared = target.read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(target.read_bytes(), prepared)


if __name__ == "__main__":
    unittest.main()
