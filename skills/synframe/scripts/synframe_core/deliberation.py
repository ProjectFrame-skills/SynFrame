"""Structural links for host judgments, not a semantic reasoner or action selector.

Agreement §§6–7,9–12,14: expose actual saved questions and feedback to the
host, and check that adoption accounts for them. No search/K/count policy.
"""

from .schema import require, ref, ACTIONS
from .graph import reference, verified


QUESTION_FIELDS = {"id", "question", "criterion_ids", "decision_impact", "important",
                   "status", "answer", "evidence_refs", "rationale", "next_action"}


def validate_question(question):
    require(type(question) is dict and set(question) == QUESTION_FIELDS,
            "information need requires " + ",".join(sorted(QUESTION_FIELDS)))
    for key in ("id", "question", "decision_impact", "rationale"):
        require(type(question[key]) is str and question[key].strip(), "empty question " + key)
    require(type(question["important"]) is bool, "question importance must be explicit")
    require(question["status"] in {"OPEN", "RESOLVED", "DEFERRED"}, "invalid question status")
    require(type(question["criterion_ids"]) is list and question["criterion_ids"]
            and all(type(x) is str and x for x in question["criterion_ids"]), "question needs goal criterion links")
    require(type(question["evidence_refs"]) is list, "question evidence must be list")
    for pointer in question["evidence_refs"]:
        ref(pointer)
    require(type(question["answer"]) is str, "question answer must be text")
    if question["status"] == "OPEN":
        require(question["next_action"] in ACTIONS, "open question needs a next reasoning action")
    else:
        require(question["next_action"] is None, "settled question has no pending action")
        if question["status"] == "RESOLVED":
            require(question["answer"].strip() and question["evidence_refs"], "resolved question needs answer and evidence")
        else:
            require(not question["important"], "important unresolved question cannot be deferred for adoption")


def questions(doc):
    if doc["type"] == "Frame":
        yield from (("frame", q) for q in doc["information_requirements"])
    if doc["type"] == "KnowledgeAsset":
        for index, understanding in enumerate(doc["understanding"]):
            yield from ((f"knowledge:{index}", q) for q in understanding["questions"])
    yield from (("capability", q) for q in doc.get("extensions", {}).get("questions", []))


def question_records(documents):
    from .learning import important_task
    docs = list(documents)
    tasks = {d["id"]: d for d in docs if d["type"] == "LearningTask"}
    records, seen = [], set()
    def record(task, key, owner):
        done = task["disposition"] in {"CLOSED", "MERGED"}
        return {"id": task["id"], "question": task["question"], "key": key,
                "owner_ref": reference(owner), "task_ref": reference(task),
                "important": important_task(task), "status": "RESOLVED" if done else task["disposition"],
                "answer": "; ".join(c["text"] for c in task["answer"]["claims"]),
                "evidence_refs": ([p for c in task["answer"]["claims"] for p in c["evidence_refs"]]
                    or task["assessment"]["evidence_refs"]),
                "rationale": task["assessment"]["rationale"], "decision_impact": task["context"]["purpose"],
                "next_action": None if done else task.get("extensions", {}).get("next_action"),
                "work_state": task["work_state"], "answer_state": task["answer"]["status"],
                "understanding_state": task["understanding"]["status"], "expansion_state": task["expansion"]["status"]}
    for doc in docs:
        if doc["validity_status"] != "VALID":
            continue
        for context, pointer in questions(doc):
            if type(pointer) is dict and set(pointer) == {"id", "revision"} and pointer["id"] in tasks:
                task = tasks[pointer["id"]]
                records.append(record(task, f"{doc['id']}/{context}/{task.get('extensions', {}).get('legacy_question_id', task['id'])}", doc))
                seen.add(task["id"])
            else:
                # Historic schema-1 questions remain inspectable, never silently upgraded.
                records.append({"key": f"{doc['id']}/{context}/legacy", "owner_ref": reference(doc),
                    "question": pointer, "status": "UNASSESSED", "important": True})
    for task in tasks.values():
        if task["id"] not in seen:
            records.append(record(task, task["id"], task))
    return records


def validate_links(doc, goal):
    """New questions reference the canonical LearningTask, never duplicate answers."""
    criteria = {c["id"] for c in goal["success_criteria"]}
    seen = set()
    for context, pointer in questions(doc):
        ref(pointer)
        key = (context, pointer["id"])
        require(key not in seen, "duplicate information need in context")
        seen.add(key)
    if doc["type"] == "Capability":
        ids = doc.get("extensions", {}).get("criterion_ids")
        require(type(ids) is list and ids and set(ids) <= criteria,
                "Capability needs extensions.criterion_ids rooted in the user outcome")


def validate_alignment(goal):
    alignment = goal.get("extensions", {}).get("goal_alignment", {})
    require(set(alignment) == {"facets", "preservation_rationale"}, "GoalSpec needs extensions.goal_alignment")
    require(type(alignment["preservation_rationale"]) is str and alignment["preservation_rationale"].strip(),
            "goal preservation needs a host rationale")
    require(type(alignment["facets"]) is list and alignment["facets"], "goal needs source facets")
    criteria = {c["id"] for c in goal["success_criteria"]}
    covered, seen = set(), set()
    for facet in alignment["facets"]:
        require(type(facet) is dict and set(facet) == {"id", "source_quote", "interpretation", "criterion_ids"},
                "goal facet requires id/source_quote/interpretation/criterion_ids")
        require(all(type(facet[k]) is str and facet[k].strip() for k in ("id", "source_quote", "interpretation")), "empty goal facet")
        require(facet["id"] not in seen, "duplicate goal facet")
        seen.add(facet["id"])
        require(facet["source_quote"] in goal["source_request"], "goal facet must cite verbatim source_request text")
        require(type(facet["criterion_ids"]) is list and facet["criterion_ids"] and set(facet["criterion_ids"]) <= criteria,
                "goal facet needs valid success criterion links")
        covered.update(facet["criterion_ids"])
    require(covered == criteria, "success criterion is disconnected from source facets")


def review_inputs(goal, candidate, documents):
    """One read-only selection of Review subjects, shared with the gate.

    Return saved facts and keys only. No PASS, sufficiency or search judgment.
    Filtering before canonical question projection is significant: an unused
    asset's question may still carry an independent goal/selection obligation.
    """
    from .learning import important_task
    documents = list(documents)
    selected = {p['id'] for p in candidate['asset_refs']}
    tasks = {d['id']: d for d in documents if d['type'] == 'LearningTask'}
    needs = [q for q in question_records(d for d in documents
        if d['type'] != 'KnowledgeAsset' or d['id'] in selected)
        if not (q.get('task_ref', {}).get('id') in tasks
            and tasks[q['task_ref']['id']]['assessment']['role'] == 'INDEPENDENT'
            and tasks[q['task_ref']['id']]['disposition'] not in {'CLOSED', 'MERGED'})]
    return {
        'goal_facets': goal.get('extensions', {}).get('goal_alignment', {}).get('facets', []),
        'capabilities': [d for d in documents if d['type'] == 'Capability'
            and d['goal_ref'] == candidate['goal_ref']
            and (d['mandatory'] or reference(d) in candidate['capability_refs'])],
        'information_needs': needs,
        'information_need_refs': [{'id': i, 'revision': r} for i, r in
            sorted({(q['owner_ref']['id'], q['owner_ref']['revision']) for q in needs})],
        'independent_followups': [d for d in tasks.values()
            if d['assessment']['role'] == 'INDEPENDENT' and important_task(d)
            and d['disposition'] not in {'CLOSED', 'MERGED'}],
    }


def review_errors(goal, candidate, review, documents, resolve):
    """Check explicit per-purpose, per-condition and per-question assessments.

    The host must still judge entailment, materiality and sufficiency. These
    bindings prevent a generic PASS and reused evidence list from hiding gaps.
    """
    errors = []
    extension = review.get("extensions", {})
    inputs = review_inputs(goal, candidate, documents)

    def assessments(name, keys):
        values = extension.get(name, {})
        if type(values) is not dict or set(values) != set(keys):
            errors.append("Review needs exact " + name + " assessments")
            return
        for key, value in values.items():
            if not (type(value) is dict and set(value) == {"status", "rationale", "evidence_refs"}
                    and value["status"] == "PASS" and type(value["rationale"]) is str
                    and value["rationale"].strip() and type(value["evidence_refs"]) is list
                    and verified(value["evidence_refs"], resolve)):
                errors.append(f"unresolved/ungrounded {name}: {key}")

    alignment = goal.get("extensions", {}).get("goal_alignment", {})
    facets = [f["id"] for f in alignment.get("facets", [])]
    if not facets:
        errors.append("goal source alignment is unassessed")
    assessments("goal_alignment", facets)
    caps = inputs['capabilities']
    assessments("capability_conditions", [d["id"] for d in caps])
    # §25.3/27.6.10/17: independence does not erase selection impact. Do not
    # require every unused-asset question to close; require a scoped assessment.
    independent = inputs['independent_followups']
    considered = extension.get("independent_followups", {})
    if type(considered) is not dict or set(considered) != {d["id"] for d in independent}:
        errors.append("Review must assess observed independent followups affecting goal/selection")
    else:
        for task in independent:
            assessment = considered[task["id"]]
            if (task["assessment"]["materiality"] == "UNKNOWN"
                    or task["assessment"]["relevance"] == "UNASSESSED"):
                errors.append("independent followup still needs observed impact scoping: " + task["id"])
            if not (type(assessment) is dict and set(assessment) == {"task_ref", "status", "decision_impact",
                    "rationale", "evidence_refs", "requeue_condition"}
                    and assessment["task_ref"] == reference(task)
                    and assessment["status"] in {"CONTINUE", "DEFER", "NO_CURRENT_EFFECT"}
                    and all(type(assessment[k]) is str and assessment[k].strip() for k in
                            ("decision_impact", "rationale", "requeue_condition"))
                    and verified(assessment["evidence_refs"], resolve)):
                errors.append("independent followup lacks current impact/requeue evidence: " + task["id"])
            elif assessment["status"] == "CONTINUE":
                errors.append("valuable independent followup still requires action: " + task["id"])
    # K questions about an unused alternative are not adoption prerequisites.
    # Frame and capability information needs remain visible across candidates.
    needs = inputs['information_needs']
    expected_refs = sorted({(q["owner_ref"]["id"], q["owner_ref"]["revision"]) for q in needs})
    pointers = extension.get("information_need_refs", [])
    actual_refs = sorted((p.get("id"), p.get("revision")) for p in pointers if type(p) is dict)
    if actual_refs != expected_refs:
        errors.append("Review information need owner revisions changed or are missing")
    assessments("question_assessments", [q["key"] for q in needs])
    for q in needs:
        if q["status"] == "UNASSESSED" or (q["important"] and q["status"] != "RESOLVED"):
            errors.append("important information gap: " + q["key"])
        elif q["status"] == "RESOLVED" and not verified(q["evidence_refs"], resolve):
            errors.append("question resolution evidence invalid: " + q["key"])
        elif not q["important"] and (not q.get("rationale") or not verified(q.get("evidence_refs", []), resolve)):
            errors.append("non-important uncertainty needs grounded impact assessment: " + q["key"])
    for pointer in candidate["asset_refs"]:
        asset = resolve(pointer)
        for k in asset["understanding"]:
            if not k["questions"] or not verified(k["evidence_refs"], resolve):
                errors.append("contextual K lacks decision/application question evidence: " + asset["id"])
    for doc, field in ((candidate, "gaps"), (review, "unresolved_items")):
        for gap in doc[field]:
            if type(gap) is dict and gap.get("important") is False:
                if not (gap.get("rationale") and type(gap.get("evidence_refs")) is list
                        and verified(gap["evidence_refs"], resolve)):
                    errors.append("minor gap lacks grounded impact/scope rationale")
    search = extension.get("search_value", {})
    if not (type(search) is dict and set(search) == {"alternatives", "stop_rationale"}
            and type(search["alternatives"]) is list and search["alternatives"]
            and type(search["stop_rationale"]) is str and search["stop_rationale"].strip()):
        errors.append("Review needs current marginal search value assessment")
    else:
        for action in search["alternatives"]:
            if not (type(action) is dict and set(action) == {"action", "expected_improvement", "cost", "rationale"}
                    and action["action"] in ACTIONS and all(type(action[k]) is str and action[k].strip()
                    for k in ("expected_improvement", "cost", "rationale"))):
                errors.append("invalid marginal search alternative")
    return errors


def review_subject_errors(goal, candidate, documents, resolve):
    """Existing Gate subject checks, available before a Review is authored.

    Presence and declared coverage are structural facts, not an assessment of
    adequate decomposition, contextual understanding or the truth of evidence.
    Both the read-only context and Gate call this same check on current records.
    """
    errors = []
    capabilities = review_inputs(goal, candidate, documents)['capabilities']
    covered = {criterion for capability in capabilities
               if capability['validity_status'] == 'VALID'
               for criterion in capability.get('extensions', {}).get('criterion_ids', [])}
    if covered != {criterion['id'] for criterion in goal['success_criteria']}:
        errors.append('goal success criteria lack capability derivation')
    for pointer in candidate['asset_refs']:
        asset = resolve(pointer)
        if not asset['understanding']:
            errors.append('no contextual understanding assessment: ' + asset['id'])
    return errors


def feedback(documents):
    """Facts derived from saved questions, never generated semantic judgments."""
    return [{"information_need": True, "key": q["key"], "description": q["question"], "important": q["important"],
             "owner_ref": q["owner_ref"], "task_ref": q.get("task_ref"), "status": q["status"],
             "next_action": q.get("next_action"), "decision_impact": q.get("decision_impact")}
            for q in question_records(documents) if q["status"] != "RESOLVED"]
