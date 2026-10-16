"""Acceptance tests exercise persistent behavior, not matching instruction text."""

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "synframe" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from synframe_core import Core, ContractError
from synframe_core.graph import reference, evaluate, pareto
from synframe_core.schema import REVIEW_CHECKS


def r(identity, revision=1):
    return {"id": identity, "revision": revision}


def goal(outcome="specification"):
    return {"id": "goal", "type": "GoalSpec", "objective": "Produce a usable verified result",
            "outcome_type": outcome, "success_criteria": [{"id": "usable", "description": "Result can be used"}],
            "explicit_constraints": [{"id": "skill", "description": "Use skills",
                "predicate": {"path": "constraint_values.delivery", "op": "eq", "value": "skills"}}],
            "inferred_requirements": [], "proposed_means": [], "source_request": "User: implement through skills.",
            "extensions": {"goal_alignment": {"facets": [{"id": "source", "source_quote": "implement through skills",
                "interpretation": "Usable implementation through skills", "criterion_ids": ["usable"]}],
                "preservation_rationale": "Explicit deterministic test goal, not a user-advice surrogate"}}}


def evidence(identity="ev", **updates):
    return {"id": identity, "type": "EvidenceRecord", "claim": "Observed functioning artifact in this environment",
            "source": "local inspection", "observation_kind": "measured", "observed_at": "2026-10-12T00:00:00Z",
            "environment": {"scope": "test fixture"}, "verification_status": "VERIFIED", "scope": "test artifact", **updates}


def capability(identity="cap", mandatory=True):
    return {"id": identity, "type": "Capability", "goal_ref": r("goal"), "name": identity,
            "inputs": [], "outputs": [], "satisfaction_conditions": "Evidence-backed capability",
            "mandatory": mandatory, "origin": "inferred", "derivation_refs": [r("goal")], "extensions": {"criterion_ids": ["usable"]}}


def asset(identity="asset", **updates):
    return {"id": identity, "type": "KnowledgeAsset", "kind": "method", "identity": identity,
            "version": "fixture-v1", "provided_capability_refs": [], "applicability": "test context",
            "understanding": [{"context": "fixture-v1 / local", "level": 3, "questions": [question("usable")],
                "evidence_refs": [r("ev")], "stop_condition": "Selection and application questions answered"}],
            "inputs": [], "outputs": [], "availability": "available", "provenance": [r("ev")], **updates}


def link(identity="link", sources=None, target="cap", relation="PROVIDES", group=None):
    return {"id": identity, "type": "DependencyLink", "sources": sources or [r("asset")],
            "target_ref": r(target), "relation": relation, "group_id": group or identity,
            "evidence_refs": [r("ev")]}


def candidate(**updates):
    return {"id": "candidate", "type": "SolutionCandidate", "goal_ref": r("goal"),
            "frame_refs": [], "asset_refs": [r("asset")], "capability_refs": [r("cap")],
            "connections": [], "gaps": [], "attributes": {"cost": None},
            "comparison_rationale": "Grounded capability path is directly testable",
            "disposition": "retain", "constraint_values": {"delivery": "skills"}, **updates}


def frame(identity="frame", **updates):
    return {"id": identity, "type": "Frame", "goal_ref": r("goal"), "object": "input records",
            "representation": "individual elements", "mechanism": "independent record processing",
            "intervention": "process source records", "evidence_refs": [r("ev")],
            "assumptions": ["independent records are sufficient"], "parent_refs": [],
            "transformation": "initial", "structural_difference": {"rationale": "Initial source representation"},
            "information_requirements": [question("structure")], **updates}


def question(identity, status="RESOLVED", important=True):
    return {"id": identity, "question": identity + " decision question", "criterion_ids": ["usable"],
            "decision_impact": "Fixture capability selection", "important": important, "status": status,
            "answer": "Measured fixture provides required result" if status == "RESOLVED" else "",
            "evidence_refs": [r("ev")], "rationale": "Explicit deterministic fixture, not autonomous evidence",
            "next_action": "DISCOVER_KNOWLEDGE" if status == "OPEN" else None}


def decision(action, evidence_refs=None):
    return {"action": action, "ddc": {"observable_state": "Current saved goal and explicit gaps",
        "decision_objective": "Resolve the directly observed gap", "available_actions": [action],
        "decision_policy": "Direct verified result at lowest observed cost", "constraints": ["Preserve user goal"],
        "state_transition": "Apply only validated records", "feedback": "Compare expected and observed result",
        "recovery": "Inspect failure and change grounded inputs before retry"},
        "alternatives": [], "evidence_refs": evidence_refs or [], "rationale": "Directly addresses the observed requirement",
        "expected_effects": ["Verified capability or explicit unresolved condition"]}


def fixture_tasks(changes, core=None, run_id=None):
    """Declared fixture judgments, explicitly not host-autonomy evidence."""
    from synframe_core.learning import basis
    from synframe_core.deliberation import validate_question
    expanded = []
    for original in changes or []:
        doc = copy.deepcopy(original)
        groups = []
        if doc["type"] == "Frame":
            groups.append(("frame", doc["information_requirements"]))
        if doc["type"] == "KnowledgeAsset":
            groups += [(f"knowledge:{i}", u["questions"]) for i,u in enumerate(doc["understanding"])]
        if doc.get("extensions", {}).get("questions"):
            groups.append(("capability", doc["extensions"]["questions"]))
        for context, entries in groups:
            for i,q in enumerate(entries):
                if set(q) == {"id", "revision"}:
                    continue
                validate_question(q)
                identity = doc["id"] + "-" + context + "-" + q["id"]
                revision = 1
                if core:
                    try: revision = core.get(run_id, identity)["revision"] + 1
                    except ContractError: pass
                resolved = q["status"] == "RESOLVED"
                task = {"id": identity, "type": "LearningTask", "goal_ref": r("goal"),
                    "question": q["question"], "subject": {"concept": "Declared structural fixture question"},
                    "context": {"purpose": q["decision_impact"], "environment": {"kind": "fixture"},
                        "version": "fixture-1", "conditions": [], "constraints": [], "scope": "bounded structural fixture"},
                    "origin_refs": [r("goal")], "goal_connections": [{"goal_ref": r("goal"), "facet_ids": ["source"],
                        "path_refs": [], "rationale": "Declared fixture goal connection"}],
                    "answer_requirements": [{"id": "ability", "ability": "Evaluate declared fixture condition",
                        "discriminator": "Read fixture observation", "sufficient_when": "Declared condition measured",
                        "evidence_requirement": "fixture evidence"}],
                    "assessment": {"relevance": "RELEVANT", "materiality": "MATERIAL" if q["important"] else "NONMATERIAL",
                        "role": "INDEPENDENT" if doc["type"] == "KnowledgeAsset" else "CRITICAL",
                        "rationale": q["rationale"], "evidence_refs": q["evidence_refs"], "unknowns": []},
                    "answer": {"status": "SUPPORTED" if resolved else "UNANSWERED", "claims": [{"id": "claim",
                        "text": q["answer"], "source_locator": "fixture declared observation", "conditions": [],
                        "inference": False, "evidence_refs": q["evidence_refs"]}] if resolved else [],
                        "counterevidence_refs": [], "gaps": [], "scope": "fixture"},
                    "understanding": {"status": "SUFFICIENT" if resolved else "UNASSESSED", "k_level": 3 if resolved else None,
                        "abilities": [{"id": "ability", "status": "MET", "evidence_refs": q["evidence_refs"],
                            "rationale": "Declared fixture ability, no autonomy claim"}] if resolved else []},
                    "expansion": {"status": "ACCOUNTED" if resolved else "UNASSESSED", "discoveries": [],
                        "scope_rationale": "Declared fixture has no external discovery space" if resolved else "Not assessed",
                        "evidence_refs": q["evidence_refs"]}, "dependency_refs": [], "work_state": "IDLE" if resolved else "READY",
                    "disposition": "CLOSED" if resolved else q["status"], "closure_assessment": {}, "reopen_conditions": [],
                    "extensions": {"legacy_question_id": q["id"], "next_action": q["next_action"]}}
                if doc["type"] == "KnowledgeAsset":
                    task["subject"] = {"asset_ref": r(doc["id"], (core.get(run_id, doc["id"])["revision"] + 1) if core and core.db.execute("SELECT 1 FROM entities WHERE run_id=? AND id=?", (run_id,doc["id"])).fetchone() else 1)}
                if resolved or q["status"] == "DEFERRED":
                    task["closure_assessment"] = {"verdict": "ANSWERED" if resolved else "DEFERRED",
                        "rationale": q["rationale"], "evidence_refs": q["evidence_refs"], "scope": "fixture",
                        "basis": basis(task), "remaining_uncertainties": [], "impact": "Bounded fixture impact",
                        "remaining_work": ["Optional fixture work"], "selected_action": "DERIVE_CAPABILITY",
                        "comparison_rationale": "Fixture priority preserves directly measured mandatory result"}
                    if not resolved: task["reopen_conditions"] = [{"condition": "fixture scope changes"}]
                expanded.append(task)
                entries[i] = r(identity, revision)
        expanded.append(doc)
    return expanded


def output(op, changes=None, outcome="SUCCEEDED", refs=None, core=None):
    return {"operation_id": op["id"], "result_refs": refs or [], "proposed_state_changes": fixture_tasks(changes, core, op["source_run_id"]),
            "evidence_refs": [], "unresolved_items": [], "observed_effects": ["Observed result recorded"],
            "next_decision_inputs": ["Reassess critical gaps"], "outcome": outcome,
            "learning_results": [], "propagation_resolutions": [], "path_assessments": []}


def declared_scope_fixture(scope):
    """Synthetic nonapplicability for unrelated core unit tests, never autonomy.

    Tool-obligation tests opt out and exercise real registration/receipt gates.
    These unit fixtures do not assert the semantic truth of a user-goal judgment.
    """
    from synframe_core.learning import basis
    doc = {k: copy.deepcopy(v) for k,v in scope.items() if k not in {
        'revision','schema_version','created_at','updated_at','source_run_id','validity_status'}}
    grounds = [r('fixture-scope-ev')]
    rationale = 'Explicit synthetic nonapplicability branch for a core unit fixture; not host behavior or user-goal evidence'
    doc['assessment'].update(relevance='NOT_RELEVANT', materiality='NONMATERIAL', evidence_refs=grounds,
                             rationale=rationale, unknowns=[])
    doc['answer'].update(status='SUPPORTED', claims=[{'id':'fixture-scope', 'text':rationale,
        'evidence_refs':grounds,'source_locator':'declared unit fixture','conditions':['Synthetic fixture only'],'inference':False}])
    doc['understanding'].update(status='SUFFICIENT', k_level=1, abilities=[{'id':n['id'], 'status':'MET',
        'evidence_refs':grounds, 'rationale':rationale} for n in doc['answer_requirements']])
    doc['expansion'].update(status='ACCOUNTED', scope_rationale=rationale, evidence_refs=grounds)
    doc.update(disposition='CLOSED', work_state='IDLE')
    doc['extensions']['next_action'] = None
    doc['closure_assessment'] = {'verdict':'NOT_APPLICABLE','rationale':rationale,'evidence_refs':grounds,
        'basis':basis(doc),'scope':'Declared unit fixture only','remaining_uncertainties':[]}
    return [evidence('fixture-scope-ev',claim=rationale),doc]


def interpretation_plan(saved):
    return {'learning_task_refs':[reference(saved)], 'learning_plan':[{
        'task_ref':reference(saved),'parent_role':'Declared interpretation fixture only',
        'gap':'Two recorded comparison paths not yet supplied',
        'requirement_ids':[n['id'] for n in saved['answer_requirements']], 'known_evidence_refs':[],
        'judgment_target':{'target_ref':reference(saved),'item_id':None,'decision':'Assess fixture records',
            'consumer_refs':[saved['goal_ref']],'scope':'Synthetic structural fixture'},
        'next_observation':{'target':'Declared fixture comparisons','source':'Local synthetic file',
            'locator':'fixture support / omission','information':'Two path bindings','decision_effect':'Fixture eligibility'},
        'sufficient_when':'Declared paths and actual record bindings exist','failure_alternative':'Retain open responsibility'}]}


def declared_interpretation_fixture(saved, raw_source, conditional=False):
    """Explicit synthetic judgments for structure tests; never autonomy evidence."""
    from synframe_core.learning import basis
    doc={k:copy.deepcopy(v) for k,v in saved.items() if k not in {
        'revision','schema_version','created_at','updated_at','source_run_id','validity_status'}}
    grounds=[r('fixture-interpretation-ev')];facets=doc['goal_connections'][0]['facet_ids']
    phrase='Declared synthetic comparison; not semantic host evidence'
    path={'target':'source support','scope':'Fixture only','source_locator':'fixture:support',
        'rationale':phrase,'facet_ids':facets,'evidence_refs':grounds}
    omission={**path,'target':'source omission','source_locator':'fixture:omission',
        'source_to_result':phrase,'result_to_source':phrase,'counterfactual_scope':phrase,
        'observed_structures':phrase,'remaining_uncertainty_assessment':phrase,'difference_ids':[]}
    interpretation={'id':'fixture-current','facet_ids':facets,'result_scope':phrase,'basis':phrase,
        'assumptions':phrase,'difference':phrase,'decision_impact':phrase,'uncertainties':phrase,
        'consumer_refs':[doc['goal_ref']],'disposition':'Declared current treatment','rationale':phrase,'reopen_condition':phrase}
    doc['extensions']['interpretation_review']={'current_interpretation':phrase,'assumptions':phrase,
        'result_properties':phrase,'support':path,'omission':omission,'interpretations':[interpretation],
        'handling':'CONDITIONAL' if conditional else 'CURRENT',
        'treatment':'Declared conditional treatment' if conditional else 'Declared current interpretation',
        'termination_scope':phrase,'effects':[{'target_ref':doc['goal_ref'],'assessment':'MAINTAIN',
            'evidence_refs':grounds,'rationale':phrase}], 'conditional_results':[
            {**{k:phrase for k in ('condition','result','method','roles','work','verification','fact_assessment','unresolved_preference_authority')},
            'evidence_refs':grounds}] if conditional else []}
    doc['assessment'].update(relevance='RELEVANT',materiality='MATERIAL',evidence_refs=grounds,rationale=phrase,unknowns=[])
    doc['answer'].update(status='SUPPORTED',claims=[{'id':'fixture-answer','text':phrase,'evidence_refs':grounds,
        'source_locator':'fixture:support and omission','conditions':['Synthetic only'],'inference':False}],gaps=[])
    doc['understanding'].update(status='SUFFICIENT',k_level=2,abilities=[{'id':n['id'],'status':'MET',
        'evidence_refs':grounds,'rationale':phrase} for n in doc['answer_requirements']])
    doc['expansion'].update(status='ACCOUNTED',scope_rationale=phrase,evidence_refs=grounds)
    doc.update(disposition='CLOSED',work_state='IDLE');doc['extensions']['next_action']=None
    doc['closure_assessment']={'verdict':'ANSWERED','rationale':phrase,'evidence_refs':grounds,
        'basis':basis(doc),'scope':'Synthetic fixture','remaining_uncertainties':[]}
    return [evidence('fixture-interpretation-ev',source=raw_source,claim=phrase),doc]


def settle_interpretation_fixture(owner):
    saved=owner.core.get(owner.run_id,'goal:goal-interpretation')
    op=owner.core.begin(owner.run_id,owner.request('DERIVE_CAPABILITY',interpretation_plan(saved)))
    raw=Path(owner.temp.name)/'interpretation-fixture.txt';raw.write_text('Synthetic source support and omission comparison, not host reasoning')
    owner.core.record_observation(owner.run_id,op['id'],owner.revision(),[{'path':str(raw),
        'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source':'Synthetic interpretation fixture'}])
    result=output(op,declared_interpretation_fixture(saved,str(raw)),core=owner.core)
    result['learning_results']=[{'task_ref':reference(saved),'result_ref':r(saved['id'],saved['revision']+1),
        'answer_refs':[r('fixture-interpretation-ev')],'understanding_change':'Declared fixture abilities',
        'discovery_ids':[],'upward_effects':['Declared fixture current goal maintenance'],
        'observations':['Actual synthetic receipt preserved'],'prediction_difference':'Fixture only'}]
    owner.core.apply(owner.run_id,op['id'],owner.core.prepare(owner.run_id,op['id'],result))


class CoreAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / ".synframe"
        self.core = Core(self.path)
        self.run = self.core.create(goal())
        self.run_id = self.run["id"]
        self.core.transition(self.run_id, "ACTIVE", 1, "Begin requested work")
        self.counter = 0
        if getattr(self, 'settle_interpretation_fixture', True):
            settle_interpretation_fixture(self)
        if getattr(self, 'settle_scope_fixture', True):
            self.put(declared_scope_fixture(self.core.get(self.run_id, 'goal:tool-scope')))

    def tearDown(self):
        self.core.close()
        self.temp.cleanup()

    def revision(self):
        return self.core.status(self.run_id)["run"]["revision"]

    def request(self, action="DERIVE_CAPABILITY", intent=None, inputs=None, grounds=None, key=None):
        self.counter += 1
        judgment = decision(action, grounds)
        observation = self.core.observe(self.run_id)
        judgment["ddc"]["observable_state"] = {"revision": observation["run"]["revision"],
            "state_digest": observation["state_digest"], "facts": ["Deterministic fixture state read"]}
        return {"action": action, "observed_revision": self.revision(), "input_refs": inputs or [],
                "constraints": ["Preserve user goal"], "evidence_refs": grounds or [],
                "decision": judgment, "intent": intent or {"task": "fixture-" + str(self.counter)},
                "idempotency_key": key or str(self.counter)}

    def put(self, changes, action="DERIVE_CAPABILITY", intent=None, grounds=None):
        op = self.core.begin(self.run_id, self.request(action, intent, grounds=grounds))
        return self.core.apply(self.run_id, op["id"], self.core.prepare(self.run_id, op["id"], output(op, changes, core=self.core)))

    def base(self):
        self.put([evidence(), capability(), asset(), link(), candidate()])

    def review(self, identity="review", changes=None):
        if getattr(self, "settle_interpretation_fixture", True) and self.core.get(self.run_id, "goal:goal-interpretation")["disposition"] == "OPEN":
            settle_interpretation_fixture(self)
        if getattr(self, 'settle_scope_fixture', True):
            scope = self.core.get(self.run_id, 'goal:tool-scope')
            if scope['disposition'] == 'OPEN':
                self.put(declared_scope_fixture(scope))
        checks = {key: {"status": "PASS", "rationale": "Verified fixture evidence covers this check", "evidence_refs": [r("ev")]} for key in REVIEW_CHECKS | {"constraint:skill"}}
        checks.update(changes or {})
        doc = {"id": identity, "type": "ReviewRecord", "candidate_ref": r("candidate"), "goal_ref": r("goal"),
               "snapshot": self.core.snapshot(self.run_id, r("candidate")), "checks": checks, "unresolved_items": [],
               "extensions": self.review_extensions()}
        self.put([doc], "REVIEW_SOLUTION")
        return r(identity)

    def review_extensions(self):
        # Deliberately prewritten fixture judgments test gate mechanics only.
        from synframe_core.deliberation import question_records
        docs = self.core.documents(self.run_id)
        selected = {p["id"] for p in self.core.get(self.run_id, "candidate")["asset_refs"]}
        tasks = {d['id']:d for d in docs if d['type']=='LearningTask'}
        needs = [q for q in question_records(d for d in docs if d['type']!='KnowledgeAsset' or d['id'] in selected)
            if not (q.get('task_ref',{}).get('id') in tasks and tasks[q['task_ref']['id']]['assessment']['role']=='INDEPENDENT'
                and tasks[q['task_ref']['id']]['disposition'] not in {'CLOSED','MERGED'})]
        check = {"status": "PASS", "rationale": "Bounded deterministic fixture observation", "evidence_refs": [r("ev")]}
        return {"verdict": "READY", "goal_alignment": {"source": check},
            "capability_conditions": {d["id"]: check for d in docs if d["type"] == "Capability" and d["mandatory"]},
            "question_assessments": {q["key"]: check for q in needs},
            "information_need_refs": list({q["owner_ref"]["id"]: q["owner_ref"] for q in needs}.values()),
            "independent_followups": {d["id"]: {"task_ref": reference(d), "status": "NO_CURRENT_EFFECT",
                "decision_impact": "Unused fixture question cannot change the directly measured selected path",
                "rationale": "Declared structural fixture independence", "evidence_refs": [r("ev")],
                "requeue_condition": "Fixture selection purpose or required condition changes"}
                for d in docs if d["type"] == "LearningTask" and d["assessment"]["role"] == "INDEPENDENT"
                and d["assessment"]["materiality"] != "NONMATERIAL"
                and d["disposition"] not in {"CLOSED", "MERGED"}},
            "search_value": {"alternatives": [{"action": "DISCOVER_KNOWLEDGE", "expected_improvement": "None for this fixture",
                "cost": "Additional fixture work", "rationale": "The declared test condition is directly measured"}],
                "stop_rationale": "Fixture inputs already determine this bounded structural test"}}

    def commit(self):
        op = self.core.begin(self.run_id, self.request("COMMIT", {"candidate_ref": r("candidate"), "review_ref": r("review")}))
        return self.core.apply(self.run_id, op["id"], self.core.prepare(self.run_id, op["id"], output(op)))

    def package(self, artifacts=None, uncertainties=None):
        doc = {"id": "package", "type": "SolutionPackage", "candidate_ref": r("candidate"), "review_ref": r("review"),
            "contents": {key: "Fixture: " + key for key in ["Goal", "RecommendedSolution", "Architecture", "RequiredKnowledge", "SelectedAssets", "DecisionRationale", "ImplementationPlan", "Constraints", "Uncertainties", "Provenance"]},
            "completion_scope": "Fixture success criterion", "artifact_refs": artifacts or [],
            "validation_refs": [r("ev")], "uncertainties": uncertainties or []}
        self.put([doc], "EXECUTE")

    def completion(self):
        return self.core.transition(self.run_id, "COMPLETED", self.revision(), "Actual criterion verified",
            verification={"usable": {"status": "PASS", "evidence_refs": [r("ev")], "rationale": "Observed usability"}}, package_ref=r("package"))

    def test_goal_requires_source_preservation_links(self):
        broken = goal(); del broken["extensions"]
        with self.assertRaisesRegex(ContractError, "goal_alignment"):
            self.core.create(broken)
        broken = goal(); broken["extensions"]["goal_alignment"]["facets"][0]["source_quote"] = "invented user request"
        with self.assertRaisesRegex(ContractError, "verbatim"):
            self.core.create(broken)

    def test_ddc_requires_observed_state_not_task_text_or_stale_digest(self):
        request = self.request()
        request["decision"]["ddc"]["observable_state"] = "Write a useful answer"
        with self.assertRaisesRegex(ContractError, "fresh observe"):
            self.core.begin(self.run_id, request)
        request = self.request()
        request["decision"]["ddc"]["observable_state"]["state_digest"] = "wrong"
        with self.assertRaisesRegex(ContractError, "fresh observe"):
            self.core.begin(self.run_id, request)

    def test_frame_need_cannot_disappear_from_feedback(self):
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request("GENERATE_FRAME"))
        result = output(op, [frame(information_requirements=[question("unknown", "OPEN")])])
        with self.assertRaisesRegex(ContractError, "unresolved information needs"):
            self.core.apply(self.run_id, op["id"], result)
        prepared = self.core.prepare(self.run_id, op["id"], result)
        self.assertEqual(prepared["unresolved_items"][0]["key"], "frame/frame/unknown")
        self.assertEqual(prepared["next_decision_inputs"][1]["next_action"], "DISCOVER_KNOWLEDGE")
        self.core.apply(self.run_id, op["id"], prepared)
        restored = self.core.restore(self.run_id)
        self.assertEqual(restored["status"]["information_needs"][0]["status"], "OPEN")

    def test_known_important_frame_gap_blocks_generic_pass_review(self):
        self.base()
        self.put([frame(information_requirements=[question("unknown", "OPEN")])], "GENERATE_FRAME")
        review = self.review()
        gate = self.core.commit_gate(self.run_id, r("candidate"), review)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("important information gap" in e for e in gate["errors"]))
        with self.assertRaisesRegex(ContractError, "Commit rejected"):
            self.core.begin(self.run_id, self.request("COMMIT", {"candidate_ref": r("candidate"), "review_ref": review}))

    def test_resolved_question_needs_answer_not_k_label(self):
        broken = question("unknown"); broken["answer"] = ""
        with self.assertRaisesRegex(ContractError, "answer and evidence"):
            self.put([evidence(), asset(understanding=[{"context": "selection", "level": 4,
                "questions": [broken], "evidence_refs": [r("ev")], "stop_condition": "label is not proof"}])])

    def test_review_must_assess_source_and_conditions_separately(self):
        self.base(); review = self.review()
        doc = self.core.get(self.run_id, "review")
        for key in ["goal_alignment", "capability_conditions", "question_assessments", "search_value"]:
            changed = {k: copy.deepcopy(v) for k,v in doc.items() if k not in {"schema_version", "created_at", "updated_at", "source_run_id", "revision", "validity_status"}}
            changed["id"] = "review-" + key
            del changed["extensions"][key]
            self.put([changed], "REVIEW_SOLUTION")
            self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r(changed["id"]))["passed"])

    def test_minor_question_may_stop_with_grounded_scope(self):
        self.base()
        self.put([frame(information_requirements=[question("optional", "DEFERRED", False)])], "GENERATE_FRAME")
        review = self.review()
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), review)["passed"])
        self.assertEqual(self.core.status(self.run_id)["information_needs"][0]["status"], "RESOLVED")
        self.assertTrue(any(q["status"] == "DEFERRED" for q in self.core.status(self.run_id)["information_needs"]))

    def test_compiler_can_correct_own_narrowing_without_fabricated_user_change(self):
        corrected = goal(); corrected["success_criteria"][0]["description"] = "Preserved usable user outcome"
        self.put([corrected], "GOAL_COMPILE", {"source_preservation_correction": "Prior wording omitted usable outcome"})
        self.assertEqual(self.core.get(self.run_id, "goal")["revision"], 2)
        corrected = goal(); corrected["source_request"] = "Different user goal"
        with self.assertRaisesRegex(ContractError, "user change source"):
            self.put([corrected], "GOAL_COMPILE", {"source_preservation_correction": "Unrelated request is not a correction"})

    def test_question_revision_invalidates_review_not_unrelated_candidate(self):
        self.base()
        self.put([frame()], "GENERATE_FRAME")
        self.review()
        changed = frame(information_requirements=[question("structure"), question("new", "OPEN")])
        result = self.put([changed], "GENERATE_FRAME")
        self.assertIn("review", result["invalidated"])
        self.assertNotIn("candidate", result["invalidated"])
        self.assertEqual(self.core.status(self.run_id)["unresolved_items"][0]["key"], "frame/frame/new")

    def test_host_io_does_not_refresh_stale_judgment_or_invent_feedback(self):
        from synframe_host import HostIO
        io = HostIO(self.path, self.run_id)
        first = self.request("GENERATE_FRAME")
        self.put([evidence()])
        with self.assertRaisesRegex(RuntimeError, "revision conflict"):
            io.begin("GENERATE_FRAME", first["decision"], first["intent"])
        current = self.request("GENERATE_FRAME")
        op = io.begin("GENERATE_FRAME", current["decision"], current["intent"])
        io.finish(op, output(op, [frame(information_requirements=[question("follow-up", "OPEN")])]))
        observed = io.call("observe")
        self.assertEqual(observed["last_result"]["unresolved_items"][0]["key"], "frame/frame/follow-up")
        self.assertEqual(observed["last_result"]["next_decision_inputs"][1]["next_action"], "DISCOVER_KNOWLEDGE")

    def test_prepare_preserves_host_conditions_and_reuses_applied_result(self):
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request("GENERATE_FRAME"))
        raw = output(op, [frame(information_requirements=[question("pending", "OPEN")])])
        condition = {"key": "external-approval", "description": "Actual independent host condition", "important": True}
        raw["unresolved_items"] = [condition]
        prepared = self.core.prepare(self.run_id, op["id"], raw)
        self.assertIn(condition, prepared["unresolved_items"])
        self.core.apply(self.run_id, op["id"], prepared)
        repeated = self.core.prepare(self.run_id, op["id"], raw)
        self.assertEqual(prepared, repeated)
        self.assertTrue(self.core.apply(self.run_id, op["id"], repeated)["duplicate"])
        self.assertIn(condition, self.core.status(self.run_id)["unresolved_items"])

    def test_executable_identity_conflict_preserves_readable_history(self):
        from unittest.mock import patch
        with patch("synframe_core.store.implementation_digest", return_value="changed-runtime"):
            self.assertFalse(self.core.status(self.run_id)["compatible"])
            self.assertEqual(self.core.get(self.run_id, "goal")["source_request"], goal()["source_request"])
            with self.assertRaisesRegex(ContractError, "contract/schema mismatch"):
                self.core.restore(self.run_id)

    def test_current_feedback_is_distinct_from_immutable_operation_history(self):
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY"))
        raw = output(op)
        raw["unresolved_items"] = ["Rendering not yet observed", "Rendering not yet observed"]
        self.core.apply(self.run_id, op["id"], raw)
        self.assertEqual(self.core.status(self.run_id)["unresolved_items"], ["Rendering not yet observed"])
        self.put([evidence("render", claim="Actual rendering observed")], "REVIEW_SOLUTION")
        state = self.core.status(self.run_id)
        self.assertFalse(state["unresolved_items"])
        self.assertEqual(next(h for h in state["operation_feedback_history"] if h["operation_ref"]["id"] == op["id"])["unresolved_items"], raw["unresolved_items"])
        self.assertEqual(self.core.restore(self.run_id)["status"], state)

    def test_schema_and_dangling_reference_rollback(self):
        op = self.core.begin(self.run_id, self.request())
        rev = self.revision()
        bad = capability(); bad["goal_ref"] = r("absent")
        with self.assertRaisesRegex(ContractError, "missing entity"):
            self.core.apply(self.run_id, op["id"], output(op, [evidence(), bad]))
        self.assertEqual(self.revision(), rev)
        with self.assertRaises(ContractError):
            self.core.get(self.run_id, "ev")
        bad = evidence(); bad["verification_status"] = "MADE_UP"
        with self.assertRaises(ContractError):
            self.core.apply(self.run_id, op["id"], output(op, [bad]))
        bad = capability(); bad["mandatory"] = "yes"
        with self.assertRaises(ContractError):
            self.core.apply(self.run_id, op["id"], output(op, [bad]))

    def test_missing_ddc_and_unsupported_action_cannot_create_intent(self):
        request = self.request()
        del request["decision"]["ddc"]["recovery"]
        rev = self.revision()
        with self.assertRaisesRegex(ContractError, "eight fields"):
            self.core.begin(self.run_id, request)
        self.assertEqual(self.revision(), rev)
        request = self.request(); request["action"] = "AUTOMATIC_BACKGROUND_RESTART"
        request["decision"]["action"] = request["action"]
        with self.assertRaises(ContractError):
            self.core.begin(self.run_id, request)

    def test_review_cannot_claim_different_dependency_snapshot(self):
        self.base()
        doc = {"id": "wrong-review", "type": "ReviewRecord", "candidate_ref": r("candidate"), "goal_ref": r("goal"),
               "snapshot": [], "extensions": {"verdict": "READY"}, "checks": {key: {"status": "PASS", "rationale": "fixture", "evidence_refs": [r("ev")]} for key in REVIEW_CHECKS}, "unresolved_items": []}
        with self.assertRaisesRegex(ContractError, "snapshot"):
            self.put([doc], "REVIEW_SOLUTION")
        with self.assertRaises(ContractError):
            self.core.get(self.run_id, "wrong-review")

    def test_external_documentation_does_not_prove_implementation_execution(self):
        self.core.close(); self.core = Core(Path(self.temp.name) / "external-proof-state")
        run = self.core.create(goal("implementation")); self.run_id = run["id"]
        self.core.transition(self.run_id, "ACTIVE", 1, "Begin")
        self.put([evidence(observation_kind="external_claim"), capability(), asset(), link(), candidate()])
        self.review(); self.commit()
        p = Path(self.temp.name) / "artifact.txt"; p.write_text("Artifact exists, but documentation alone does not verify its execution")
        self.package(artifacts=[{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "source": "fixture"}])
        with self.assertRaisesRegex(ContractError, "directly observed"):
            self.completion()

    def test_idempotent_intent_and_apply(self):
        request = self.request()
        op = self.core.begin(self.run_id, request)
        self.assertEqual(self.core.begin(self.run_id, request)["id"], op["id"])
        result = output(op, [evidence()])
        first = self.core.apply(self.run_id, op["id"], result)
        second = self.core.apply(self.run_id, op["id"], result)
        self.assertTrue(first["applied"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["revision"], second["revision"])
        result["observed_effects"] = ["different result"]
        with self.assertRaises(ContractError):
            self.core.apply(self.run_id, op["id"], result)
        request["intent"]["task"] = "different work"
        with self.assertRaises(ContractError):
            self.core.begin(self.run_id, request)

    def test_optimistic_write_conflict(self):
        request = self.request()
        op = self.core.begin(self.run_id, request)
        with self.assertRaisesRegex(ContractError, "revision conflict"):
            other = Core(self.path)
            try:
                other.begin(self.run_id, {**request, "idempotency_key": "other"})
            finally:
                other.close()
        self.core.apply(self.run_id, op["id"], output(op))

    def test_and_or_and_requires(self):
        self.put([evidence(), capability("a", False), capability("b", False), capability("root"),
                  asset(), link("provides-a", target="a"),
                  link("and", [r("a"), r("b")], "root", "AND", "joint"),
                  candidate(capability_refs=[r("root")])])
        check = lambda: evaluate(self.core.get(self.run_id, "candidate"), self.core.documents(self.run_id), lambda p: self.core.resolve(self.run_id, p))
        self.assertEqual(check()["missing"], ["root"])
        self.put([link("provides-b", target="b")])
        self.assertFalse(check()["missing"])
        self.put([capability("pre", False), link("prereq", [r("pre")], "root", "REQUIRES")])
        self.assertEqual(check()["missing"], ["root"])
        self.put([link("provides-pre", target="pre")])
        self.assertFalse(check()["missing"])
        # A different OR path does not require both alternatives.
        self.put([capability("or-root"), link("or", [r("a"), r("pre")], "or-root", "OR", "alternatives")])
        self.assertIn("or-root", check()["satisfied"])

    def test_cycles_and_enables_do_not_ground_capabilities(self):
        self.put([evidence(), capability("a"), capability("b", False), asset(),
                  link("cycle-a", [r("b")], "a", "AND"), link("cycle-b", [r("a")], "b", "AND"),
                  link("enables", target="a", relation="ENABLES"), candidate(capability_refs=[r("a")])])
        state = evaluate(self.core.get(self.run_id, "candidate"), self.core.documents(self.run_id), lambda p: self.core.resolve(self.run_id, p))
        self.assertEqual(state["missing"], ["a"])

    def test_grouped_hyperedge_requires_all_sources(self):
        self.put([evidence(), capability(), asset(), asset("other", availability="unavailable"),
                  link("joint-1", [r("asset")], "cap", "AND", "joint"),
                  link("joint-2", [r("other")], "cap", "AND", "joint"), candidate(asset_refs=[r("asset"), r("other")])])
        self.review()
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_scoped_transitive_invalidation_and_observation_history(self):
        self.base(); self.review()
        self.put([evidence("unrelated"), asset("unrelated-asset", provenance=[r("unrelated")], understanding=[{"context": "other", "level": 2, "questions": [], "evidence_refs": [r("unrelated")], "stop_condition": "comparison only"}])])
        change = evidence(claim="New observation changes prior applicability")
        result = self.put([change])
        self.assertIn("candidate", result["invalidated"])
        self.assertIn("review", result["invalidated"])
        self.assertEqual(self.core.get(self.run_id, "unrelated-asset")["validity_status"], "VALID")
        self.assertEqual(self.core.get(self.run_id, "ev", 1)["claim"], "Observed functioning artifact in this environment")
        self.assertEqual(self.core.get(self.run_id, "ev")["revision"], 2)
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_simplification_invalidates_old_review(self):
        self.base(); self.review()
        doc = candidate(comparison_rationale="Same functions with simpler implementation")
        self.put([doc], "SIMPLIFY")
        self.assertEqual(self.core.get(self.run_id, "review")["validity_status"], "STALE")
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate", 2), r("review"))["passed"])

    def test_unselected_alternative_does_not_block_or_invalidate_selected_path(self):
        self.base()
        self.put([evidence("other-ev"), asset("other", provenance=[r("other-ev")]),
                  {**link("other-path", [r("other")]), "evidence_refs": [r("other-ev")]}])
        self.review()
        result = self.put([evidence("other-ev", claim="Other unselected approach no longer applicable")])
        self.assertNotIn("candidate", result["invalidated"])
        self.assertNotIn("review", result["invalidated"])
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_unused_knowledge_question_remains_visible_without_forcing_completion_work(self):
        self.base()
        self.put([asset("unselected", understanding=[{"context": "Unselected alternative", "level": 1,
            "questions": [question("unused", "OPEN")], "evidence_refs": [r("ev")],
            "stop_condition": "Unselected; compare only if decision value warrants"}])])
        self.review(); self.commit()
        artifact = Path(self.temp.name) / "actual.txt"; artifact.write_text("Verified fixture artifact")
        self.package([{"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "source": "Actual fixture file"}])
        self.assertEqual(self.completion()["state"], "COMPLETED")
        self.assertTrue(any(q["key"] == "unselected/knowledge:0/unused" for q in self.core.status(self.run_id)["information_needs"]))

    def test_archive_stale_candidate_preserves_history(self):
        self.base()
        self.put([evidence(claim="Changed applicability")])
        self.put([{**candidate(), "validity_status": "ARCHIVED", "disposition": "archive"}])
        self.assertEqual(self.core.get(self.run_id, "candidate")["validity_status"], "ARCHIVED")
        self.assertEqual(self.core.get(self.run_id, "candidate", 1)["validity_status"], "VALID")

    def test_successful_discovery_reframe_has_all_stages_and_no_superiority_precondition(self):
        self.put([evidence(), frame()])
        steps = {"assumptions": ["Independent record processing may lose shared constraints"], "axis": "representation",
                 "structural_difference": "shared constraints instead of independent records",
                 "information_requirements": ["record dependencies", "constraint states"],
                 "graph_changes": ["derive constraint evaluation capability"], "dependent_judgments": ["element-only candidates"],
                 "validity_changes": ["review affected candidates"], "rediscovery_scope": ["shared record constraints"]}
        new = frame("rules-frame", representation="record dependency graph", mechanism="joint constraint evaluation",
                    intervention="map record dependencies to platform resources", parent_refs=[r("frame")], transformation="representation",
                    structural_difference={"rationale": "different mechanism and information needs"},
                    information_requirements=[question("roles"), question("states")])
        self.put([new], "REFRAME", {"trigger": "Discovery", "steps": steps}, [r("ev")])
        self.assertEqual(self.core.get(self.run_id, "rules-frame")["parent_refs"], [r("frame")])
        self.assertEqual(self.core.get(self.run_id, "frame")["validity_status"], "VALID")
        # Parent remains historical after a scoped assumption revision.
        self.put([frame(assumptions=["Revised source assumption"])])
        self.assertEqual(self.core.get(self.run_id, "rules-frame")["validity_status"], "VALID")

    def test_noop_frame_and_missing_reframe_stages_rejected(self):
        self.put([evidence(), frame()])
        op = self.core.begin(self.run_id, self.request("REFRAME", {"trigger": "Discovery"}, grounds=[r("ev")]))
        with self.assertRaises(ContractError):
            self.core.apply(self.run_id, op["id"], output(op, [frame("noop", parent_refs=[r("frame")])]))
        with self.assertRaisesRegex(ContractError, "all recorded stages"):
            self.core.apply(self.run_id, op["id"], output(op, [frame("different", mechanism="different mechanism", parent_refs=[r("frame")])]))

    def test_minor_uncertainty_does_not_become_new_mandatory_condition(self):
        self.base(); self.review(); self.commit()
        self.package(uncertainties=[{"description": "Optional future optimization not measured", "important": False, "rationale": "No effect on directly measured fixture success", "evidence_refs": [r("ev")]}])
        self.assertEqual(self.completion()["state"], "COMPLETED")

    def test_graph_proof_invalidation_reaches_candidate_without_copied_link_refs(self):
        self.put([evidence(), evidence("proof"), capability(), asset(),
                  {**link(), "evidence_refs": [r("proof")]}, candidate()])
        self.review()
        result = self.put([evidence("proof", claim="New proof changes capability applicability")])
        self.assertIn("candidate", result["invalidated"])
        self.assertIn("review", result["invalidated"])
        self.assertEqual(self.core.get(self.run_id, "asset")["validity_status"], "VALID")

    def test_candidate_cannot_omit_mandatory_capability(self):
        self.base(); self.review()
        self.put([capability("forgotten")])
        gate = self.core.commit_gate(self.run_id, r("candidate"), r("review"))
        self.assertFalse(gate["passed"])
        self.assertIn("dependencies changed", " ".join(gate["errors"]))

    def test_missing_capability_commit_rejected_and_logged(self):
        self.put([evidence(), capability(), asset(), candidate()])
        self.review()
        with self.assertRaisesRegex(ContractError, "missing mandatory"):
            self.commit()
        events = self.core.explain(self.run_id)["events"]
        self.assertEqual(events[-1]["kind"], "REJECTED_INTENT")
        self.assertEqual(self.core.status(self.run_id)["run"]["state"], "ACTIVE")

    def test_semantic_unknown_does_not_pass_commit(self):
        self.base()
        self.review(changes={"knowledge": {"status": "UNKNOWN", "rationale": "Compatibility not known", "evidence_refs": [r("ev")]}})
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_declared_review_condition_controls_gate_without_new_schema(self):
        # Host-declared important conditions reuse checks. No domain, tool,
        # expected recommendation or semantic truth is inferred by the core.
        self.base()
        for status, grounds, passes in [("FAIL", [r("ev")], False),
                                        ("UNKNOWN", [r("ev")], False),
                                        ("PASS", [], False),
                                        ("PASS", [r("ev")], True)]:
            with self.subTest(status=status, grounded=bool(grounds)):
                pointer = self.review("review-declared-" + status + str(bool(grounds)), {
                    "connection:cap": {"status": status,
                        "rationale": "Explicit fixture condition for this candidate connection",
                        "evidence_refs": grounds}})
                gate = self.core.commit_gate(self.run_id, r("candidate"), pointer)
                self.assertEqual(gate["passed"], passes)
                if not passes:
                    self.assertTrue(any("connection:cap" in error for error in gate["errors"]))

    def test_explicit_constraint_cannot_be_overridden_by_review(self):
        self.put([evidence(), capability(), asset(), link(), candidate(constraint_values={"delivery": "MCP server"})])
        self.review()
        self.assertIn("explicit constraint", " ".join(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["errors"]))

    def test_asset_name_without_evidence_or_understanding_is_not_enough(self):
        self.put([evidence(), capability(), asset(provenance=[], understanding=[]), link(), candidate()])
        self.review()
        gate = self.core.commit_gate(self.run_id, r("candidate"), r("review"))
        self.assertFalse(gate["passed"])
        self.assertIn("understanding", " ".join(gate["errors"]))

    def test_io_mismatch_and_unbound_input(self):
        self.put([evidence(), capability(), asset(outputs=[{"name": "output", "type": "OutputData"}]),
                  asset("mapper", inputs=[{"name": "source", "type": "CSS"}]), link(),
                  candidate(asset_refs=[r("asset"), r("mapper")], connections=[{
                      "from_ref": r("asset"), "output": "output", "to_ref": r("mapper"),
                      "input": "source", "evidence_refs": [r("ev")]}])])
        self.review()
        errors = " ".join(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["errors"])
        self.assertIn("incompatible", errors)
        self.assertIn("unbound", errors)

    def test_conflicting_assets_reject_commit(self):
        self.put([evidence(), capability(), asset(), asset("other"), link(),
                  link("conflict", [r("asset")], "other", "CONFLICTS"), candidate(asset_refs=[r("asset"), r("other")])])
        self.review()
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])

    def test_valid_commit_does_not_mark_execution_complete(self):
        self.base(); self.review()
        self.assertTrue(self.commit()["gate"]["passed"])
        self.assertEqual(self.core.status(self.run_id)["run"]["state"], "ACTIVE")
        self.package()
        self.assertEqual(self.completion()["state"], "COMPLETED")
        with self.assertRaises(ContractError):
            self.core.transition(self.run_id, "ACTIVE", self.revision(), "overwrite finished run")

    def test_implementation_completion_requires_actual_artifact_and_observation(self):
        self.core.close(); self.core = Core(Path(self.temp.name) / "implementation-state")
        run = self.core.create(goal("implementation")); self.run_id = run["id"]
        self.core.transition(self.run_id, "ACTIVE", 1, "Begin")
        self.base(); self.review(); self.commit()
        self.package()
        with self.assertRaisesRegex(ContractError, "artifact locations"):
            self.completion()
        p = Path(self.temp.name) / "result.txt"; p.write_text("usable result")
        artifact = {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "source": "host execution"}
        doc = self.core.get(self.run_id, "package")
        updated = {k: v for k, v in doc.items() if k not in {"schema_version", "revision", "created_at", "updated_at", "source_run_id", "validity_status"}}
        updated["artifact_refs"] = [artifact]
        self.put([updated], "EXECUTE")
        self.assertEqual(self.core.transition(self.run_id, "COMPLETED", self.revision(), "Artifact inspected",
            verification={"usable": {"status": "PASS", "evidence_refs": [r("ev")], "rationale": "Actual output inspected"}}, package_ref=r("package", 2))["state"], "COMPLETED")

    def test_execute_requires_actual_adoption_not_only_a_ready_review(self):
        self.base(); self.review()
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])
        before = self.revision()
        operations = self.core.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        decisions = [d for d in self.core.documents(self.run_id) if d["type"] == "DecisionRecord"]
        with self.assertRaisesRegex(ContractError, "EXECUTE needs a current committed"):
            self.core.begin(self.run_id, self.request("EXECUTE", {
                "candidate_ref": r("candidate"), "review_ref": r("review"), "task": "Generate requested result"}))
        self.assertEqual(self.revision(), before)
        self.assertEqual(self.core.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], operations)
        self.assertEqual([d for d in self.core.documents(self.run_id) if d["type"] == "DecisionRecord"], decisions)
        rejected = self.core.explain(self.run_id)["events"][-1]
        self.assertEqual(rejected["kind"], "REJECTED_INTENT")
        self.assertEqual(rejected["data"]["action"], "EXECUTE")
        self.commit()
        self.assertFalse(any(d["type"] == "SolutionPackage" for d in self.core.documents(self.run_id)))
        op = self.core.begin(self.run_id, self.request("EXECUTE", {
            "candidate_ref": r("candidate"), "review_ref": r("review"), "task": "Generate requested result"}))
        self.assertEqual(op["action"], "EXECUTE")

    def test_execute_rejects_changed_adopted_candidate(self):
        self.base(); self.review(); self.commit()
        self.put([candidate(comparison_rationale="Changed route requires current adoption")])
        with self.assertRaisesRegex(ContractError, "EXECUTE adoption rejected:.*stale reference"):
            self.core.begin(self.run_id, self.request("EXECUTE", {"task": "Generate requested result"}))

    def test_execute_rejects_changed_adopted_review(self):
        self.base(); self.review(); self.commit()
        self.review()
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), r("review", 2))["passed"])
        with self.assertRaisesRegex(ContractError, "EXECUTE adoption rejected:.*stale reference"):
            self.core.begin(self.run_id, self.request("EXECUTE", {"task": "Generate requested result"}))

    def test_execute_rechecks_gate_when_adopted_refs_stay_current(self):
        self.base(); self.review(); self.commit()
        self.put([frame("new-frame", information_requirements=[question("new-material-gap", "OPEN")])], "GENERATE_FRAME")
        self.assertEqual(self.core.resolve(self.run_id, r("candidate"))["revision"], 1)
        self.assertEqual(self.core.resolve(self.run_id, r("review"))["revision"], 1)
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])
        with self.assertRaisesRegex(ContractError, "EXECUTE adoption rejected"):
            self.core.begin(self.run_id, self.request("EXECUTE", {"task": "Generate requested result"}))

    def test_execute_cannot_name_a_different_current_route_than_the_adoption(self):
        self.base(); self.review(); self.commit()
        self.put([candidate(id="other-candidate")])
        self.review(identity="other-review")
        self.assertTrue(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])
        for key, pointer in (("candidate_ref", r("other-candidate")), ("review_ref", r("other-review"))):
            with self.subTest(key=key), self.assertRaisesRegex(ContractError, "differs from the committed solution"):
                self.core.begin(self.run_id, self.request("EXECUTE", {key: pointer, "task": "Generate requested result"}))

    def test_pre_adoption_reasoning_can_preserve_an_actual_probe_artifact(self):
        self.assertIsNone(self.core.work_context(self.run_id)["adoption"]["committed_candidate_ref"])
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {
            "task": "Probe the local output capability before selecting a solution"}))
        p = Path(self.temp.name) / "capability-probe.txt"; p.write_text("Observed prototype output")
        artifact = {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "source": "Capability probe"}
        self.core.record_observation(self.run_id, op["id"], self.revision(), [artifact])
        pending = self.core.restore(self.run_id)["status"]["pending_operations"][0]
        self.assertEqual(pending["action"], "DERIVE_CAPABILITY")
        self.assertEqual(pending["extensions"]["actual_observations"], [artifact])
        self.assertFalse(pending["result"])
        self.assertIsNone(self.core.work_context(self.run_id)["adoption"]["committed_candidate_ref"])

    def test_future_evidence_b3_time_pair_rejected_atomically_with_pending_observation(self):
        # Exact B3 observed_at/core-time pair in a new isolated structural
        # fixture, not a replay or modification of the original B3 run.
        op = self.core.begin(self.run_id, self.request())
        source = Path(self.temp.name) / "scope-observation.json"
        source.write_text('{"observed_at":"2026-10-16T08:24:00+00:00"}')
        artifact = {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "source": "Original future-time fixture input, not a corrected observation"}
        self.core.record_observation(self.run_id, op["id"], self.revision(), [artifact])
        result = output(op, [evidence("earlier-patch"), evidence("future",
            source=str(source), observed_at="2026-10-16T08:24:00+00:00")])
        original_result = copy.deepcopy(result)
        before = self.core.restore(self.run_id)
        for mode in ("apply", "preflight"):
            with self.subTest(mode=mode), patch("synframe_core.store.now",
                    return_value="2026-10-16T08:23:28.478168+00:00"):
                with self.assertRaisesRegex(ContractError, "future.*observed_at is later"):
                    if mode == "apply":
                        self.core.apply(self.run_id, op["id"], result)
                    else:
                        self.core.preflight(self.run_id, op["id"], result)
            self.assertEqual(self.core.restore(self.run_id), before)
            self.assertEqual(result, original_result)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), artifact["sha256"])
        self.assertFalse(self.core.get(self.run_id, op["id"])["applied"])
        self.assertEqual(self.core.get(self.run_id, op["id"])["extensions"]["actual_observations"], [artifact])
        self.assertFalse(any(d["id"] in {"future", "earlier-patch"} for d in self.core.documents(self.run_id)))

    def test_evidence_time_keeps_past_same_instant_and_unqualified_representations(self):
        values = ["2026-10-12T00:00:00Z", "2026-10-16T08:23:28.478168Z",
                  "2026-10-16T10:23:28.478168+02:00", "2026-10-16T03:23:28.478168-05:00",
                  "unknown", "2026-10-17T08:24:00", "between collection and assessment"]
        op = self.core.begin(self.run_id, self.request())
        result = output(op, [evidence("time-" + str(i), observed_at=value) for i,value in enumerate(values)])
        with patch("synframe_core.store.now", return_value="2026-10-16T08:23:28.478168+00:00"):
            check = self.core.preflight(self.run_id, op["id"], result)
            self.assertTrue(check["validated"])
            self.assertFalse(self.core.get(self.run_id, op["id"])["applied"])
            self.core.apply(self.run_id, op["id"], check["prepared_result"])
        for i,value in enumerate(values):
            self.assertEqual(self.core.get(self.run_id, "time-" + str(i))["observed_at"], value)

    def test_existing_error_history_can_be_read_and_restored_without_wallclock_judgment(self):
        # Simulate a pre-guard stored error only inside this current-identity
        # fixture. Real old runs still require their matching preserved package.
        with patch("synframe_core.store._validate_evidence_time"), patch("synframe_core.store.now",
                return_value="2026-10-16T08:23:28.478168+00:00"):
            self.put([evidence("historical-error", observed_at="2026-10-16T08:24:00+00:00")])
        original = self.core.get(self.run_id, "historical-error")
        with patch("synframe_core.store.now", side_effect=AssertionError("read must not obtain a new clock")):
            self.assertEqual(self.core.get(self.run_id, "historical-error"), original)
            restored = self.core.restore(self.run_id)
            observed = self.core.work_context(self.run_id)
        self.assertIn(original, restored["snapshot"]["documents"])
        self.assertEqual(observed["revision"], self.revision())

    def test_execute_exact_idempotent_reuse_returns_saved_result_after_gate_changes(self):
        self.base(); self.review(); self.commit()
        request = self.request("EXECUTE", {"task": "Generate requested result"}, key="adopted-execution")
        op = self.core.begin(self.run_id, request)
        self.core.apply(self.run_id, op["id"], self.core.prepare(self.run_id, op["id"], output(op)))
        self.put([frame("later-frame", information_requirements=[question("later-material-gap", "OPEN")])], "GENERATE_FRAME")
        self.assertFalse(self.core.commit_gate(self.run_id, r("candidate"), r("review"))["passed"])
        before = self.revision()
        operations = self.core.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        reused = self.core.begin(self.run_id, request)
        self.assertEqual(reused["id"], op["id"])
        self.assertTrue(reused["applied"])
        self.assertEqual(reused["result"]["outcome"], "SUCCEEDED")
        self.assertEqual(self.revision(), before)
        self.assertEqual(self.core.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], operations)
        with self.assertRaisesRegex(ContractError, "EXECUTE adoption rejected"):
            self.core.begin(self.run_id, self.request("EXECUTE", {"task": "New execution after gate changed"}))

    def test_checkpoint_restore_pending_and_completed_work(self):
        self.base()
        op = self.core.begin(self.run_id, self.request("EXPAND_COMPOSITION", {"task": "Observe composition change"}))
        before = self.core.restore(self.run_id)
        self.core.close(); self.core = Core(self.path)
        after = self.core.restore(self.run_id)
        self.assertEqual(before, after)
        self.assertEqual(after["status"]["pending_operations"][0]["id"], op["id"])
        self.assertTrue(any(d["type"] == "SolutionCandidate" for d in after["snapshot"]["documents"]))
        with self.assertRaisesRegex(ContractError, "pending"):
            self.core.resume(self.run_id, self.revision(), "resume", [r("ev")])
        self.core.apply(self.run_id, op["id"], output(op))
        self.assertFalse(self.core.restore(self.run_id)["status"]["pending_operations"])

    def test_recovery_inspection_in_suspended_state_and_resume(self):
        self.put([evidence()])
        self.core.transition(self.run_id, "SUSPENDED", self.revision(), "Host closing")
        with self.assertRaises(ContractError):
            self.core.transition(self.run_id, "ACTIVE", self.revision(), "Guess recovered")
        self.put([evidence("recovered", claim="Host available; no pending external effects")], "RECOVERY_INSPECT")
        run = self.core.resume(self.run_id, self.revision(), "Cause resolved", [r("recovered")])
        self.assertEqual(run["state"], "ACTIVE")

    def test_unknown_external_effect_needs_inspection_not_reexecution(self):
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "External capability probe effect"}))
        self.core.apply(self.run_id, op["id"], output(op, outcome="UNKNOWN"))
        self.assertEqual(len(self.core.status(self.run_id)["pending_operations"]), 1)
        self.core.reconcile(self.run_id, op["id"], self.revision(), [r("ev")], "effects_inspected", "Actual remote state inspected")
        self.assertFalse(self.core.status(self.run_id)["pending_operations"])

    def test_stale_pending_result_must_be_reconciled(self):
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "Pending capability probe"}))
        self.put([evidence("inspection")], "RECOVERY_INSPECT")
        with self.assertRaisesRegex(ContractError, "revision conflict"):
            self.core.apply(self.run_id, op["id"], output(op))
        self.core.reconcile(self.run_id, op["id"], self.revision(), [r("inspection")], "not_executed", "Inspection confirms work never ran")
        self.assertFalse(self.core.status(self.run_id)["pending_operations"])

    def test_retry_identical_failure_requires_new_evidence(self):
        op = self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "Capability probe"}))
        failed = output(op, outcome="FAILED"); failed["unresolved_items"] = ["Temporary probe condition unresolved"]
        self.core.apply(self.run_id, op["id"], failed)
        self.assertEqual(len(self.core.status(self.run_id)["unresolved_items"]), 1)
        with self.assertRaisesRegex(ContractError, "retry evidence"):
            self.core.begin(self.run_id, self.request("DERIVE_CAPABILITY", {"task": "Capability probe"}))
        self.put([evidence("retry", claim="Temporary failure cleared")], "RECOVERY_INSPECT")
        request = self.request("DERIVE_CAPABILITY", {"task": "Capability probe", "retry_evidence_refs": [r("retry")]})
        retried = self.core.begin(self.run_id, request)
        self.assertEqual(retried["action"], "DERIVE_CAPABILITY")
        self.core.apply(self.run_id, retried["id"], output(retried))
        self.assertFalse(self.core.status(self.run_id)["unresolved_items"])
        self.assertTrue(any(e["data"].get("outcome") == "FAILED" for e in self.core.explain(self.run_id)["events"]))

    def test_contract_and_database_version_mismatch(self):
        run = self.core._run(self.run_id)
        run["contract_digest"] = "old-contract"
        self.core.db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(run), self.run_id))
        self.assertFalse(self.core.status(self.run_id)["compatible"])
        with self.assertRaisesRegex(ContractError, "mismatch"):
            self.core.restore(self.run_id)
        self.core.db.execute("UPDATE metadata SET value='999' WHERE key='schema_version'")
        with self.assertRaisesRegex(ContractError, "schema mismatch"):
            Core(self.path)

    def test_checkpoint_corruption_detected(self):
        self.core.db.execute("UPDATE checkpoints SET digest='tampered' WHERE run_id=?", (self.run_id,))
        with self.assertRaisesRegex(ContractError, "integrity"):
            self.core.restore(self.run_id)

    def test_pareto_unknown_not_zero_and_no_fixed_width(self):
        result = pareto({"quality": 9, "cost": None}, {"quality": 8, "cost": 2}, {"quality": "max", "cost": "min"})
        self.assertFalse(result["left_dominates"])
        self.assertEqual(result["unknown"], ["cost"])
        self.assertTrue(pareto({"quality": 9, "cost": 1}, {"quality": 8, "cost": 2}, {"quality": "max", "cost": "min"})["left_dominates"])
        with self.assertRaises(ContractError):
            pareto({"quality": float("inf")}, {"quality": 8}, {"quality": "max"})

    def test_reframe_only_four_grounded_triggers(self):
        self.put([evidence()])
        for trigger in ["Initial", "Discovery", "Deficiency", "Stagnation"]:
            op = self.core.begin(self.run_id, self.request("REFRAME", {"trigger": trigger}, grounds=[r("ev")]))
            # A failed/duplicate Frame is recorded without claiming adoption.
            self.core.apply(self.run_id, op["id"], output(op, outcome="UNKNOWN"))
        with self.assertRaisesRegex(ContractError, "trigger"):
            self.core.begin(self.run_id, self.request("REFRAME", {"trigger": "every_three_steps"}, grounds=[r("ev")]))

    def test_goal_change_requires_explicit_source_and_invalidates_dependents(self):
        self.base()
        with self.assertRaisesRegex(ContractError, "Goal Compiler"):
            self.put([goal()], "EXPAND_COMPOSITION")
        result = self.put([{**goal(), "objective": "Explicit revised user goal"}], "GOAL_COMPILE", {"user_change_source": "User explicitly revised the goal"})
        self.assertIn("candidate", result["invalidated"])
        self.assertEqual(self.core.status(self.run_id)["run"]["goal_ref"], r("goal", 2))

    def test_cancel_and_partial_are_not_completed(self):
        self.core.transition(self.run_id, "PARTIAL", self.revision(), "Resource limit, required gaps remain")
        self.assertEqual(self.core.result(self.run_id)["state"], "PARTIAL")
        with self.assertRaises(ContractError):
            self.core.begin(self.run_id, self.request())

    def test_cli_six_modes_and_errors(self):
        cli = [sys.executable, str(SCRIPTS / "synframe.py"), "--state", str(self.path)]
        for mode in ["status", "resume", "result", "explain"]:
            result = subprocess.run(cli + [mode, "--run", self.run_id], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
        result = subprocess.run(cli + ["get", "--run", self.run_id, "--id", "missing"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stderr)["applied"])
        cancel = Path(self.temp.name) / "cancel.json"; cancel.write_text('{"reason":"User cancelled"}')
        result = subprocess.run(cli + ["cancel", "--run", self.run_id, "--expected", str(self.revision()), "--input", str(cancel)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
