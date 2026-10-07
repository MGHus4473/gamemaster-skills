"""Synthetic intent/precondition regressions; no accounts or live requests."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ptty_operations", ROOT / "ptty-skill/scripts/operation_catalog.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class OperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ops.load_catalog()

    def step(self, operation, **kwargs):
        return ops.preflight(self.catalog, {"operations": [operation], **kwargs})["steps"][0]

    def test_ambiguous_score_search_exposes_correction_and_clear(self):
        ids = {x["id"] for x in ops.search(self.catalog, "比分")}
        self.assertTrue({"live.score", "live.clear_score"} <= ids)

    def test_substitute_search_and_missing_current_entry_require_readback(self):
        self.assertIn('roster.edit', {x['id'] for x in ops.search(self.catalog, '替补')})
        self.assertIn('roster_current_entry_verified', self.step('roster.edit', mode='requested_changes')['facts_to_read'])

    def test_retired_roster_entry_cannot_pass_preflight(self):
        facts = {k: True for k in ops.resolve(self.catalog, 'roster.edit')['requires']}
        facts['roster_current_entry_verified'] = False
        step = self.step('roster.edit', mode='requested_changes', facts=facts)
        self.assertIn('precondition_unsatisfied', step['blocked_by'])

    def test_signup_transfer_is_separate_from_plan_edit(self):
        transfer = ops.resolve(self.catalog, "entries.transfer")
        self.assertIn("group_mapping", transfer["requires"])
        self.assertIn("payments", ops.resolve(self.catalog, "entries.withdraw")["impacts"])
        self.assertNotEqual(transfer["route"], ops.resolve(self.catalog, "plan.edit")["route"])

    def test_move_does_not_invent_regenerate_delete_or_payment_steps(self):
        result = ops.preflight(self.catalog, {"operations": ["schedule.move"], "mode": "requested_changes"})
        self.assertEqual([x["operation"] for x in result["steps"]], ["schedule.move"])
        self.assertFalse(result["execution_authorized"])

    def test_unknown_facts_trigger_read_not_false_or_automatic_generation(self):
        step = self.step("matches.generate", mode="requested_changes")
        self.assertIn("plan_confirmed", step["facts_to_read"])
        self.assertEqual(step["failed_facts"], [])
        self.assertEqual(step["next_step"], "read_missing_facts")

    def test_false_fact_blocks_even_in_change_mode(self):
        step = self.step("schedule.move", mode="requested_changes", facts={"scheduling_valid": False})
        self.assertIn("precondition_unsatisfied", step["blocked_by"])
        self.assertEqual(step["failed_facts"], ["scheduling_valid"])

    def test_readonly_rejects_all_side_effect_classes(self):
        for operation in self.catalog["operations"]:
            with self.subTest(operation=operation["id"]):
                step = self.step(operation["id"])
                if operation["kind"] in {"write", "notify", "financial", "account", "compute"}:
                    self.assertIn("outside_readonly_scope", step["blocked_by"])
                elif operation["kind"] == "read":
                    self.assertNotIn("outside_readonly_scope", step["blocked_by"])

    def test_demo_wizard_and_random_checks_never_accepted(self):
        for name in ("demo.check", "demo.wizard"):
            for mode in ("readonly", "requested_changes"):
                self.assertIn("demonstration_or_unimplemented", self.step(name, mode=mode)["blocked_by"])

    def test_lock_requires_fee_evidence(self):
        self.assertIn("fee_authorized", self.step("roster.lock", mode="requested_changes")["facts_to_read"])
        self.assertEqual(ops.resolve(self.catalog, "roster.quote")["kind"], "read")

    def test_export_with_renumbering_is_not_a_readonly_download(self):
        step = self.step("matches.export_renumber")
        self.assertIn("outside_readonly_scope", step["blocked_by"])
        self.assertIn("renumber_scope", step["facts_to_read"])
        self.assertEqual(ops.resolve(self.catalog, "reports.export")["kind"], "read")

    def test_score_correction_requires_downstream_review(self):
        step = self.step("live.score", mode="requested_changes")
        self.assertIn("downstream_reviewed", step["facts_to_read"])
        self.assertTrue({"advancement", "reports"} <= set(step["recheck_after_change"]))

    def test_duplicate_component_names_resolve_different_routes(self):
        matches = ops.resolve(self.catalog, "matches.read")
        schedule = ops.resolve(self.catalog, "schedule.read")
        self.assertNotEqual(matches["route"], schedule["route"])
        self.assertIn("TrialSsBpIndex", schedule["component"])
        self.assertEqual(matches["component"], "TrialSsBpIndex")

    def test_complete_facts_never_claim_authorization_or_backend_validation(self):
        item = ops.resolve(self.catalog, "schedule.move")
        result = ops.preflight(self.catalog, {"mode": "requested_changes", "operations": [item["id"]],
                                              "facts": {x: True for x in item["requires"]}})
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["steps"][0]["evidence"], "static")
        self.assertEqual(result["steps"][0]["next_step"], "verify_current_form_and_task_scope")

    def test_notifications_and_visibility_do_not_share_scope(self):
        self.assertIn("notification_scope", ops.resolve(self.catalog, "control.notify_send")["requires"])
        self.assertNotIn("notification_scope", ops.resolve(self.catalog, "publish.visibility")["requires"])

    def test_unknown_or_duplicate_operation_rejected(self):
        for ids in (["unknown.action"], ["schedule.move", "schedule.move"], []):
            with self.assertRaises(ValueError):
                ops.preflight(self.catalog, {"operations": ids})

    def test_facts_are_not_free_text_or_truthy_strings(self):
        for facts in ({"target_identity": "true"}, {"role_access": 1}, {"invented": True}, []):
            with self.assertRaises(ValueError):
                self.step("schedule.move", facts=facts)

    def test_request_rejects_extraneous_payloads(self):
        with self.assertRaises(ValueError):
            ops.preflight(self.catalog, {"operations": ["reports.export"], "extra_payload": "synthetic"})


if __name__ == "__main__":
    unittest.main()
