"""v3.2 state/action contracts. All judgments here are declared fixtures."""
import copy
import json
import unittest
import test_core as fixtures
from test_core import ( fixture_tasks, frame, question, evidence, capability,
                       asset, link, candidate, output, r, ContractError)
from synframe_core.learning import basis
from synframe_core.graph import reference, evaluate


def task(identity="task", closed=False):
    q = question("q", "RESOLVED" if closed else "OPEN")
    doc = fixture_tasks([frame(identity, information_requirements=[q])])[0]
    doc["id"] = identity
    doc["extensions"].pop("legacy_question_id", None)
    if closed:
        doc["closure_assessment"]["basis"] = basis(doc)
    return doc


def body(doc):
    return {k:copy.deepcopy(v) for k,v in doc.items() if k not in {
        "revision", "schema_version", "created_at", "updated_at", "source_run_id", "validity_status"}}


def dep(identity, revision=1, required=True, role="ANSWER_DEPENDS_ON"):
    return {"source_ref": r(identity, revision), "role": role, "required": required,
            "scope": "actual fixture need", "rationale": "Declared fixture dependency"}


class LearningAcceptance(unittest.TestCase):
    setUp = fixtures.CoreAcceptance.setUp
    tearDown = fixtures.CoreAcceptance.tearDown
    revision = fixtures.CoreAcceptance.revision
    request = fixtures.CoreAcceptance.request
    put = fixtures.CoreAcceptance.put
    base = fixtures.CoreAcceptance.base
    review = fixtures.CoreAcceptance.review
    review_extensions = fixtures.CoreAcceptance.review_extensions

    def learn(self, identity, changed, resolutions=None):
        saved = self.core.get(self.run_id, identity)
        from synframe_core.learning import dependencies
        consumers = [edge.get('target_ref', reference(doc)) for doc in self.core.documents(self.run_id)
                     for edge in dependencies(doc) if edge['source_ref']['id'] == identity
                     and edge['role'] != 'DISCOVERED_FROM']
        req = self.request("DEEPEN_KNOWLEDGE", {"learning_task_refs": [reference(saved)],
            "learning_plan": [{"task_ref": reference(saved), "parent_role": "Fixture dependency",
                "gap": "Declared unresolved ability", "next_observation": {"target":"Fixture required condition", "source":"Declared fixture evidence",
                    "locator":"fixture:ev", "information":"Condition present or absent", "decision_effect":"Fixture ability assessment"},
                "requirement_ids":[n["id"] for n in saved["answer_requirements"]], "known_evidence_refs":[r("ev")],
                "judgment_target":{"target_ref":reference(saved), "item_id":None, "decision":"Evaluate fixture ability",
                    "consumer_refs": consumers or [reference(saved)], "scope":"Bounded fixture"},
                "sufficient_when": "Required fixture ability is supported", "failure_alternative": "Different fixture path"}]})
        op = self.core.begin(self.run_id, req)
        result = output(op, changed, core=self.core)
        result["learning_results"] = [{"task_ref": reference(saved), "result_ref": r(identity, saved["revision"]+1),
            "answer_refs": [r("ev")], "understanding_change": "Declared fixture ability now grounded",
            "discovery_ids": [d["id"] for d in next(d for d in changed if d["id"]==identity)["expansion"]["discoveries"]],
            "upward_effects": ["Reassess actual fixture consumer"], "observations": ["Fixture evidence inspected"],
            "prediction_difference": "Declared fixture result; no autonomous judgment claim"}]
        result["propagation_resolutions"] = resolutions or []
        return self.core.apply(self.run_id, op["id"], self.core.prepare(self.run_id, op["id"], result))

    def test_learning_axes_and_closure_are_independent(self):
        self.put([evidence(), task()])
        broken = task(closed=True); broken["understanding"]["abilities"][0]["status"] = "UNKNOWN"
        with self.assertRaisesRegex(ContractError, "unmet required abilities"):
            self.put([broken])
        broken = task(closed=True); broken["answer"]["status"] = "PROVISIONAL"
        broken["closure_assessment"]["basis"] = basis(broken)
        with self.assertRaisesRegex(ContractError, "supported answer"):
            self.put([broken])

    def test_sufficient_unit_must_end_and_cannot_be_rescheduled(self):
        self.put([evidence(), task()])
        broken = task(closed=True); broken["disposition"] = "OPEN"; broken["work_state"] = "READY"
        with self.assertRaisesRegex(ContractError, "must end"):
            self.put([broken])
        self.learn("task", [task(closed=True)])
        state = self.core.observe(self.run_id)
        self.assertFalse(state["learning_frontier"]["ready"])
        self.assertIn(r("task",2), [i['task_ref'] for i in state["learning_frontier"]["ended"]])
        with self.assertRaisesRegex(ContractError, "cannot be scheduled"):
            self.learn("task", [task(closed=True)])

    def test_important_discovery_requires_actual_followup(self):
        self.put([evidence()])
        doc = task(closed=True)
        item = {"id":"found", "source_locator":"fixture observation", "content":"New unresolved prerequisite",
            "observation_kind":"measured", "novelty":"Not previously represented", "parent_connection":"Affects required ability", "understanding_gap":"Unresolved prerequisite condition",
            "assessment":"UNKNOWN", "disposition":None, "target_refs":[], "rationale":"Not evaluated", "reopen_condition":""}
        doc["expansion"]["discoveries"] = [item]; doc["closure_assessment"]["basis"] = basis(doc)
        with self.assertRaisesRegex(ContractError, "unhandled discover"):
            self.put([doc])
        item.update(disposition="PREREQUISITE",target_refs=[r("child")])
        doc["closure_assessment"]["basis"] = basis(doc)
        with self.assertRaisesRegex(ContractError, "required dependency"):
            self.put([task("child"), doc])
        doc["dependency_refs"] = [dep("child")]; doc["closure_assessment"]["basis"] = basis(doc)
        with self.assertRaisesRegex(ContractError, "critical unfinished"):
            self.put([task("child"), doc])

    def test_recursive_chain_executes_descendants_and_returns_to_goal(self):
        # A test depth is a fixture, never a runtime depth policy. Each unit is
        # actually intent/applied and each upward assessment changes its parent.
        depth = 7
        docs = [evidence()]
        for i in range(depth):
            doc = task("unit-"+str(i))
            if i < depth-1:
                doc["dependency_refs"] = [dep("unit-"+str(i+1))]
                doc["work_state"] = "WAITING"
            docs.append(doc)
        docs.append(link("root-impact", [r("unit-0")], "goal", "AFFECTS"))
        self.put(docs)
        self.assertEqual(len(self.core.observe(self.run_id)["learning_frontier"]["ready"]),1)
        for i in reversed(range(depth)):
            identity="unit-"+str(i)
            closed = task(identity,True)
            if i < depth-1: closed["dependency_refs"]=[dep("unit-"+str(i+1),2)]
            closed["closure_assessment"]["basis"]=basis(closed)
            resolutions=[]
            for o in self.core.status(self.run_id)["propagation_obligations"]:
                if o["status"]=="PENDING" and o["target_ref"]["id"]==identity:
                    resolutions.append({"id":o["id"],"assessment":"REVISE","evidence_refs":[r("ev")],
                        "rationale":"Child result is applied to this parent's required ability",
                        "result_refs":[r(identity,2)],"remaining_work":[]})
            self.learn(identity,[closed],resolutions)
        obligations=self.core.status(self.run_id)["propagation_obligations"]
        root=[o for o in obligations if o["status"]=="PENDING" and o["target_ref"]["id"]=="goal"]
        self.assertEqual(len(root),1)
        op=self.core.begin(self.run_id,self.request("REVIEW_SOLUTION"))
        result=output(op);result["propagation_resolutions"]=[{"id":root[0]["id"],"assessment":"MAINTAIN",
            "evidence_refs":[r("ev")],"rationale":"Original fixture goal preserved after child-to-parent propagation",
            "result_refs":[r("goal")],"remaining_work":[]}]
        self.core.apply(self.run_id,op["id"],self.core.prepare(self.run_id,op["id"],result))
        state=self.core.restore(self.run_id)["status"]
        self.assertEqual(len([i for i in state["learning_frontier"]["ended"] if i['task_ref']['id'].startswith('unit-')]),depth)
        self.assertFalse(state["learning_frontier"]["ready"])
        self.assertFalse([o for o in state["propagation_obligations"] if o["status"]=="PENDING"])

    def test_path_end_does_not_answer_question_and_pause_is_not_completion(self):
        self.put([evidence(),task()])
        op=self.core.begin(self.run_id,self.request("REVIEW_SOLUTION"))
        result=output(op);result["path_assessments"]=[{"id":"path-a","task_ref":r("task"),"verdict":"PATH_END",
            "rationale":"Observed fixture path has no discriminating information","evidence_refs":[r("ev")],"next_paths":["Other source"]}]
        self.core.apply(self.run_id,op["id"],self.core.prepare(self.run_id,op["id"],result))
        self.assertEqual(self.core.get(self.run_id,"task")["disposition"],"OPEN")
        doc=task();doc["work_state"]="PAUSED";doc["reopen_conditions"]=[{"condition":"Observed access returns"}]
        doc["closure_assessment"]={"verdict":"CONSTRAINT","rationale":"Actual fixture access constraint",
            "evidence_refs":[r("ev")],"basis":basis(doc),"scope":"fixture","remaining_uncertainties":["Required ability"],
            "impact":"Question unanswered","remaining_work":["Inspect alternative source"]}
        self.put([doc]);state=self.core.restore(self.run_id)["status"]
        self.assertFalse(state["learning_frontier"]["ready"])
        self.assertEqual(state["learning_frontier"]["paused_or_deferred"][0]["disposition"],"OPEN")
        self.assertEqual(len(state["path_assessments"]),1)

    def test_closed_unit_reopens_only_for_material_observed_change(self):
        self.put([evidence(),task(closed=True)])
        reopened=task()
        with self.assertRaisesRegex(ContractError,"reopening condition"):
            self.put([reopened])
        self.put([evidence("counter",claim="New observed contradiction changes required ability")])
        reopened["answer"]["status"]="CONFLICTED"
        reopened["answer"]["counterevidence_refs"]=[r("counter")]
        reopened["extensions"]["reopen_event"]={"kind":"COUNTEREVIDENCE","rationale":"New contradiction of needed condition","evidence_refs":[r("counter")]}
        self.put([reopened]);self.assertEqual(len(self.core.observe(self.run_id)["learning_frontier"]["ready"]),1)

    def test_pending_upward_blocks_gate_and_survives_reopen(self):
        self.base();self.put([task("child"),link("impact",[r("child")],"candidate","AFFECTS")]);self.review()
        self.learn("child",[task("child",True)])
        state=self.core.restore(self.run_id)["status"]
        self.assertTrue(any(o["status"]=="PENDING" for o in state["propagation_obligations"]))
        self.assertFalse(self.core.commit_gate(self.run_id,r("candidate"),r("review"))["passed"])

    def test_shared_or_catalog_unused_member_change_preserves_selected_proof(self):
        self.put([evidence(),evidence("other-ev"),capability(),asset(),asset("other",provenance=[r("other-ev")]),
            link("or",[r("asset"),r("other")],"cap","OR","one"),candidate()]);self.review()
        result=self.put([evidence("other-ev",claim="Unused alternative changes")])
        self.assertNotIn("or",result["invalidated"]);self.assertNotIn("candidate",result["invalidated"])
        self.assertNotIn("review",result["invalidated"])
        self.assertTrue(self.core.commit_gate(self.run_id,r("candidate"),r("review"))["passed"])
        self.assertNotIn("other",[p["id"] for p in self.core.snapshot(self.run_id,r("candidate"))])

    def test_capability_and_unknown_condition_conflicts_block_gate(self):
        self.put([evidence(),capability("left"),capability("right"),asset(),link("a",target="left"),link("b",target="right"),
            link("conflict",[r("left")],"right","CONFLICTS"),candidate(capability_refs=[r("left"),r("right")])]);self.review()
        gate=self.core.commit_gate(self.run_id,r("candidate"),r("review"))
        self.assertFalse(gate["passed"]);self.assertIn("conflict",gate["coverage"]["conflicts"])
        self.assertIn("conflict",[p["id"] for p in self.core.snapshot(self.run_id,r("candidate"))])

    def test_exact_closure_basis_and_merge_obligations(self):
        self.put([evidence()]);doc=task(closed=True);doc["context"]["version"]="Changed environment"
        with self.assertRaisesRegex(ContractError,"stale snapshot"):
            self.put([doc])
        self.put([task("source"),task("target")]);merged=task("source")
        merged["disposition"]="MERGED";merged["work_state"]="IDLE"
        merged["reopen_conditions"]=[{"condition":"Source-specific requirement changes"}]
        merged["closure_assessment"]={"verdict":"REUSED","rationale":"Fixture proposed reuse","evidence_refs":[r("ev")],
            "basis":basis(merged),"scope":"fixture","remaining_uncertainties":[],"target_ref":r("target"),"compatibility":"Declared scope"}
        with self.assertRaisesRegex(ContractError,"reopen obligations"):
            self.put([merged])

    def test_unverified_applicability_conflict_is_not_compatibility(self):
        unknown = link("unknown-conflict", [r("condition")], "cap", "CONFLICTS")
        unknown["evidence_refs"] = [r("applicability")]
        self.put([evidence(), evidence("condition"), evidence("applicability", verification_status="UNVERIFIED"),
            capability(), asset(), link(), unknown,
            candidate(extensions={"condition_refs":[r("condition")]})])
        self.review()
        gate=self.core.commit_gate(self.run_id,r("candidate"),r("review"))
        self.assertFalse(gate["passed"])
        self.assertIn("unknown-conflict",gate["coverage"]["conflicts"])

    def test_counterevidence_must_be_handled_and_remain_in_history(self):
        self.put([evidence(),evidence("counter")]);doc=task(closed=True)
        doc["answer"]["counterevidence_refs"]=[r("counter")]
        doc["closure_assessment"]["basis"]=basis(doc)
        with self.assertRaisesRegex(ContractError,"counterevidence"):
            self.put([doc])
        doc["answer"]["counterevidence_assessments"]=[{"counter_ref":r("counter"),"disposition":"OUT_OF_SCOPE",
            "rationale":"Fixture counter has a different applicability condition","evidence_refs":[r("ev")]}]
        doc["closure_assessment"]["basis"]=basis(doc);self.put([doc])
        self.assertEqual(self.core.get(self.run_id,"task")["answer"]["counterevidence_refs"],[r("counter")])

    def test_comparison_change_preserves_function_and_invalidates_selection(self):
        self.put([evidence(),evidence("comparison"),capability(),asset(),link(),candidate(extensions={
            "judgment_dependencies":[dep("comparison",role="COMPARES_USING",required=False)]})]);self.review()
        self.put([evidence("comparison",claim="Compared alternative has a new observed constraint")])
        current=self.core.get(self.run_id,"candidate")
        self.assertEqual(current["validity_status"],"VALID")
        self.assertEqual(current["extensions"]["selection_validity"],"STALE")
        proof=evaluate(current,self.core.documents(self.run_id),lambda p:self.core.resolve(self.run_id,p))
        self.assertFalse(proof["missing"])
        self.assertFalse(self.core.commit_gate(self.run_id,reference(current),r("review"))["passed"])

    def test_conservative_migration_preserves_old_records_and_reassesses(self):
        # Build a schema-1 history in an isolated fixture, never mutate real runs.
        self.core.close()
        from synframe_core.store import Core,encode
        self.core=Core(self.path)
        old=self.core._run(self.run_id,compatible=False);old["schema_version"]=1;old["contract_version"]="3.1"
        self.core.db.execute("UPDATE runs SET data=? WHERE id=?",(encode(old),self.run_id))
        before=self.core.explain(self.run_id)
        migrated=self.core.migrate(self.run_id)
        self.assertTrue(migrated["origin_preserved"])
        self.assertEqual(before,self.core.explain(self.run_id))
        self.assertEqual(self.core._run(migrated["run"]["id"])["contract_version"],"3.2")
        self.assertTrue(all(t["disposition"]=="OPEN" and t["understanding"]["status"]=="UNASSESSED"
            for t in self.core.status(migrated["run"]["id"])["learning_tasks"]))

    def test_observation_plan_requires_ability_target_and_discriminating_location(self):
        self.put([evidence(), task()])
        plan = {"task_ref": r("task"), "parent_role": "Fixture selection", "gap": "Unresolved condition",
            "requirement_ids": ["ability"], "known_evidence_refs": [r("ev")],
            "judgment_target": {"target_ref": r("task"), "item_id": "ability", "decision": "Use bounded answer",
                "consumer_refs": [r("goal")], "scope": "Fixture context"},
            "next_observation": {"target": "Fixture condition", "source": "Fixture observation",
                "locator": "fixture:condition", "information": "Condition present or absent", "decision_effect": "Answer validity"},
            "sufficient_when": "Condition grounded", "failure_alternative": "Different observation source"}
        for field, replacement, message in [("requirement_ids", ["absent"], "ability IDs"),
                ("next_observation", "Read more", "next observation"),
                ("judgment_target", {**plan["judgment_target"], "item_id": "absent"}, "item ID absent")]:
            broken = {**plan, field: replacement}
            with self.assertRaisesRegex(ContractError, message):
                self.core.begin(self.run_id, self.request("DEEPEN_KNOWLEDGE",
                    {"learning_task_refs": [r("task")], "learning_plan": [broken]}))
        op = self.core.begin(self.run_id, self.request("DEEPEN_KNOWLEDGE",
            {"learning_task_refs": [r("task")], "learning_plan": [plan]}))
        self.assertEqual(self.core.restore(self.run_id)["status"]["pending_operations"][0]["intent"]["learning_plan"], [plan])

    def test_observation_survives_interruption_without_fabricated_assessment(self):
        import hashlib
        from synframe_core.store import Core
        self.put([evidence(), task()])
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "Observe external capability result"}))
        raw = self.path / "raw.txt"; raw.write_text("Actual fixture tool output; not yet assessed")
        artifact = {"path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "source": "Fixture actual output"}
        self.core.record_observation(self.run_id, op["id"], self.revision(), [artifact])
        revision = self.revision()
        self.core.record_observation(self.run_id, op["id"], revision, [artifact])
        self.assertEqual(self.revision(), revision)
        self.core.close(); self.core = Core(self.path)
        restored = self.core.restore(self.run_id)["status"]
        pending = restored["pending_operations"][0]
        self.assertEqual(pending["extensions"]["actual_observations"], [artifact])
        self.assertEqual(pending["result"], {})
        self.assertEqual(self.core.get(self.run_id, "task")["understanding"]["status"], "UNASSESSED")
        self.core.apply(self.run_id, op["id"], self.core.prepare(self.run_id, op["id"], output(op)))
        self.assertFalse(self.core.status(self.run_id)["pending_operations"])
        another = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "Other capability observation"}))
        raw.write_text("Changed after hash")
        with self.assertRaisesRegex(ContractError, "artifact changed"):
            self.core.record_observation(self.run_id, another["id"], self.revision(), [artifact])

    def test_object_update_cannot_hide_a_learning_gap(self):
        self.put([evidence(), capability()])
        doc = task()
        doc["expansion"] = {"status": "ACCOUNTED", "scope_rationale": "Fixture observed a missing premise",
            "evidence_refs": [r("ev")], "discoveries": [{"id": "gap", "source_locator": "fixture:premise",
                "content": "New applicability premise", "observation_kind": "measured", "novelty": "Missing premise",
                "parent_connection": "Needed for fixture applicability", "understanding_gap": "Premise not understood",
                "assessment": "MATERIAL", "disposition": "UPDATE", "target_refs": [r("cap")],
                "rationale": "Changing capability alone does not answer premise", "reopen_condition": ""}]}
        with self.assertRaisesRegex(ContractError, "UPDATE cannot hide"):
            self.put([doc])
        child = task("child")
        doc["expansion"]["discoveries"][0]["target_refs"].append(r("child"))
        self.put([child, doc])
        self.assertEqual(len(self.core.status(self.run_id)["learning_frontier"]["ready"]), 2)

    def test_required_ability_change_needs_observed_reason(self):
        self.put([evidence(), task()])
        changed = task(); changed["answer_requirements"][0]["sufficient_when"] = "Different actual condition"
        with self.assertRaisesRegex(ContractError, "changed ability criteria"):
            self.put([changed])
        changed["extensions"]["requirements_change"] = {"rationale": "Fixture observation exposed new condition", "evidence_refs": [r("ev")]}
        self.put([changed])
        self.assertEqual(self.core.get(self.run_id, "task")["answer_requirements"], changed["answer_requirements"])

    def test_review_must_account_for_independent_selection_questions(self):
        self.base()
        self.put([task("independent")])
        doc = body(self.core.get(self.run_id, "independent")); doc["assessment"]["role"] = "INDEPENDENT"
        self.put([doc]); self.review()
        review = body(self.core.get(self.run_id, "review"))
        review["id"] = "missing-independent"; review["extensions"].pop("independent_followups")
        self.put([review], "REVIEW_SOLUTION")
        self.assertIn("independent followups", " ".join(self.core.commit_gate(self.run_id, r("candidate"), r(review["id"]))["errors"]))
        review["id"] = "continue-independent"; review["extensions"] = self.review_extensions()
        review["extensions"]["independent_followups"]["independent"]["status"] = "CONTINUE"
        self.put([review], "REVIEW_SOLUTION")
        self.assertIn("still requires action", " ".join(self.core.commit_gate(self.run_id, r("candidate"), r(review["id"]))["errors"]))
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_needs_work_must_register_actual_unfinished_task(self):
        self.base(); self.review()
        review = body(self.core.get(self.run_id, "review")); review["id"] = "needs-work"
        review["extensions"]["verdict"] = "NEEDS_WORK"
        with self.assertRaisesRegex(ContractError, "register actual followup"):
            self.put([review], "REVIEW_SOLUTION")
        self.put([task("followup")]); review["snapshot"] = self.core.snapshot(self.run_id, r("candidate"))
        review["extensions"]["followup_refs"] = [r("followup")]
        self.put([review], "REVIEW_SOLUTION")
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("needs-work"))["passed"])

    def test_needs_work_can_link_actual_dependency_update_without_new_learning(self):
        self.base(); self.review()
        review = body(self.core.get(self.run_id, "review")); review["id"] = "dependency-review"
        review["extensions"]["verdict"] = "NEEDS_WORK"
        review["extensions"]["followup_refs"] = [r("new-impact")]
        update = link("new-impact", [r("ev")], "cap", "AFFECTS")
        self.put([update, review], "REVIEW_SOLUTION")
        self.assertEqual(self.core.get(self.run_id, "new-impact")["revision"], 1)
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("dependency-review"))["passed"])

    def test_unknown_independent_impact_cannot_be_deferred_into_ready(self):
        self.base()
        independent = task("unknown-independent")
        independent["assessment"].update(role="INDEPENDENT", materiality="UNKNOWN", unknowns=["Selection impact not observed"])
        self.put([independent]); self.review()
        gate = self.core.commit_gate(self.run_id, r("candidate"), r("review"))
        self.assertFalse(gate["passed"])
        self.assertIn("impact scoping", " ".join(gate["errors"]))

if __name__=="__main__":unittest.main()
