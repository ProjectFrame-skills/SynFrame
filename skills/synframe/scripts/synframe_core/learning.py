"""v3.2 learning state, role-scoped dependencies and termination invariants.

No model, semantic scoring or action selection lives here. Host assessments are
checked against explicit evidence bindings and observable saved state.
"""

import hashlib
import json
from .schema import require, ref, ACTIONS
from .graph import reference, verified

ROLES = {"DISCOVERED_FROM", "ANSWER_DEPENDS_ON", "SUPPORTS", "REFUTES",
         "AFFECTS", "COMPARES_USING", "USES_PROOF", "REUSES"}
PROOF_ROLES = {"ANSWER_DEPENDS_ON", "SUPPORTS", "REFUTES", "USES_PROOF", "REUSES"}
AXES = {"answer": {"UNANSWERED", "PROVISIONAL", "SUPPORTED", "CONFLICTED", "REFUTED"},
        "understanding": {"UNASSESSED", "INSUFFICIENT", "SUFFICIENT", "STALE"},
        "expansion": {"UNASSESSED", "PENDING", "ACCOUNTED", "STALE"}}
DISPOSITIONS = {"CREATE_TASK", "REUSE", "PREREQUISITE", "UPDATE", "EXCLUDE", "DEFER"}
REOPEN = {"COUNTEREVIDENCE", "CONTEXT_CHANGED", "PARENT_NEED", "EVIDENCE_INVALID", "SCOPE_CHANGED"}
OBSERVATION_FIELDS = {"target", "source", "locator", "information", "decision_effect"}
JUDGMENT_FIELDS = {"target_ref", "item_id", "decision", "consumer_refs", "scope"}
DISCOVERY_FIELDS = {"id", "source_locator", "content", "observation_kind", "novelty",
    "parent_connection", "understanding_gap", "assessment", "disposition", "target_refs",
    "rationale", "reopen_condition"}


def validate_plan(plan, task, resolve):
    """§27.6.3/6/12: check bindings, never infer discriminating value."""
    ids = {n["id"] for n in task["answer_requirements"]}
    selected = plan.get("requirement_ids")
    require(type(selected) is list and selected and len(selected) == len(set(selected))
            and set(selected) <= ids, "learning plan needs exact required ability IDs")
    observation = plan.get("next_observation")
    require(type(observation) is dict and set(observation) == OBSERVATION_FIELDS,
            "next observation needs target/source/locator/information/decision_effect")
    for key in OBSERVATION_FIELDS:
        nonempty(observation[key], "next observation " + key)
    target = plan.get("judgment_target", {})
    require(type(target) is dict and set(target) == JUDGMENT_FIELDS,
            "learning needs an exact judgment target, decision, consumers and scope")
    owner = resolve(target["target_ref"])
    require(target["item_id"] is None or type(target["item_id"]) is str and target["item_id"].strip(),
            "judgment item ID must be stable or null for whole object")
    if target["item_id"] is not None:
        def contains(value):
            if isinstance(value, dict):
                return value.get("id") == target["item_id"] or any(contains(v) for v in value.values())
            return isinstance(value, list) and any(contains(v) for v in value)
        require(contains(owner), "judgment item ID absent from exact target version")
    for key in ("decision", "scope"):
        nonempty(target[key], "judgment " + key)
    require(type(target["consumer_refs"]) is list and target["consumer_refs"], "judgment needs actual consumers")
    for pointer in target["consumer_refs"]:
        resolve(pointer)
    evidence_list(plan.get("known_evidence_refs"))
    for pointer in plan["known_evidence_refs"]:
        require(resolve(pointer)["type"] == "EvidenceRecord", "known grounds must be evidence")


def nonempty(value, label):
    require(type(value) is str and value.strip(), label + " requires substantive text")


def evidence_list(value):
    require(type(value) is list, "evidence_refs must be a list")
    for pointer in value:
        ref(pointer)


def basis(task):
    """Closure is bound to the actual needs, answers, discoveries and dependencies."""
    payload = {k: task[k] for k in ("goal_ref", "question", "subject", "context",
        "goal_connections", "answer_requirements", "assessment", "answer",
        "understanding", "expansion", "dependency_refs")}
    if "interpretation_review" in task.get("extensions", {}):
        payload["interpretation_review"] = task["extensions"]["interpretation_review"]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def semantic_content(doc):
    """A bookkeeping/ref revision alone must not cause infinite upward propagation."""
    ignored = {"revision", "created_at", "updated_at", "schema_version", "source_run_id",
               "provenance", "closure_assessment", "work_state", "reopen_conditions"}
    def clean(value):
        if isinstance(value, dict):
            if set(value) == {"id", "revision"}:
                return {"id": value["id"]}
            return {k: clean(v) for k, v in value.items() if k not in ignored}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean(doc)


def dependencies(doc):
    """Declared provider → consumer edges. Discovery lineage is history only."""
    if doc["type"] == "LearningTask":
        for dep in doc["dependency_refs"]:
            yield dep
        for kind, items in (("claim", doc["answer"]["claims"]), ("ability", doc["understanding"]["abilities"])):
            for item in items:
                for pointer in item["evidence_refs"]:
                    yield {"source_ref": pointer, "role": "USES_PROOF", "required": True,
                        "scope": kind + "/" + item["id"], "rationale": "Actual claim/ability evidence binding"}
    elif doc["type"] == "DependencyLink" and doc["relation"] in ROLES:
        for pointer in doc["sources"]:
            yield {"source_ref": pointer, "role": doc["relation"], "required":
                   doc["relation"] in PROOF_ROLES, "scope": doc["group_id"],
                   "rationale": "Explicit role-scoped DependencyLink", "target_ref": doc["target_ref"]}
    for dep in doc.get("extensions", {}).get("judgment_dependencies", []):
        yield dep


def validate_shape(task):
    nonempty(task["question"], "learning question")
    subject = task["subject"]
    require(type(subject) is dict and (set(subject) == {"concept"} or set(subject) == {"asset_ref"}),
            "learning subject requires concept or asset_ref")
    if "asset_ref" in subject:
        ref(subject["asset_ref"])
    else:
        nonempty(subject["concept"], "unknown concept")
    context = task["context"]
    require(set(context) == {"purpose", "environment", "version", "conditions", "constraints", "scope"},
            "learning context needs purpose/environment/version/conditions/constraints/scope")
    for key in ("purpose", "version", "scope"):
        nonempty(context[key], "context " + key)
    require(type(context["environment"]) is dict and type(context["conditions"]) is list
            and type(context["constraints"]) is list, "invalid learning context")
    require(task["origin_refs"] and task["goal_connections"], "learning needs origin and inherited goal connections")
    for connection in task["goal_connections"]:
        require(type(connection) is dict and {"goal_ref", "facet_ids", "path_refs", "rationale"} == set(connection),
                "goal connection needs goal_ref/facet_ids/path_refs/rationale")
        ref(connection["goal_ref"])
        require(type(connection["facet_ids"]) is list and connection["facet_ids"], "learning needs source facet IDs")
        require(type(connection["path_refs"]) is list, "inherited goal path must be a list")
        for p in connection["path_refs"]:
            ref(p)
        nonempty(connection["rationale"], "inherited goal path")
    require(task["answer_requirements"], "learning needs required abilities and discriminators")
    ids = set()
    for need in task["answer_requirements"]:
        require(type(need) is dict and set(need) == {"id", "ability", "discriminator", "sufficient_when", "evidence_requirement"},
                "invalid answer requirement")
        for key, value in need.items():
            nonempty(value, "answer requirement " + key)
        require(need["id"] not in ids, "duplicate answer requirement")
        ids.add(need["id"])
    a = task["assessment"]
    require(set(a) == {"relevance", "materiality", "role", "rationale", "evidence_refs", "unknowns"}, "invalid learning assessment")
    require(a["relevance"] in {"RELEVANT", "POSSIBLE", "UNASSESSED", "NOT_RELEVANT"}, "invalid relevance")
    require(a["materiality"] in {"MATERIAL", "NONMATERIAL", "UNKNOWN"}, "invalid materiality")
    require(a["role"] in {"CRITICAL", "SELECTION", "INDEPENDENT", "SCOPING"}, "invalid learning role")
    nonempty(a["rationale"], "learning impact rationale")
    evidence_list(a["evidence_refs"])
    require(type(a["unknowns"]) is list, "assessment unknowns must be a list")
    for field, states in AXES.items():
        require(type(task[field]) is dict and task[field].get("status") in states, "invalid " + field + " state")
    answer = task["answer"]
    require({"status", "claims", "counterevidence_refs", "gaps", "scope"} <= set(answer)
            and set(answer) <= {"status", "claims", "counterevidence_refs", "gaps", "scope", "counterevidence_assessments"}, "invalid learning answer")
    require(type(answer["claims"]) is list and type(answer["gaps"]) is list, "invalid claims/gaps")
    evidence_list(answer["counterevidence_refs"])
    for assessment in answer.get("counterevidence_assessments", []):
        require(set(assessment) == {"counter_ref", "disposition", "rationale", "evidence_refs"}, "invalid counterevidence handling")
        ref(assessment["counter_ref"])
        require(assessment["counter_ref"] in answer["counterevidence_refs"] and
                assessment["disposition"] in {"RESOLVED", "OUT_OF_SCOPE", "UNRESOLVED"}, "counter assessment lost observed counter")
        nonempty(assessment["rationale"], "counterevidence rationale")
        evidence_list(assessment["evidence_refs"])
    for claim in answer["claims"]:
        require(type(claim) is dict and set(claim) == {"id", "text", "evidence_refs", "source_locator", "conditions", "inference"}, "invalid claim binding")
        for k in ("id", "text", "source_locator"):
            nonempty(claim[k], "claim " + k)
        evidence_list(claim["evidence_refs"])
        require(type(claim["conditions"]) is list and type(claim["inference"]) is bool, "invalid claim conditions/inference")
    u = task["understanding"]
    require(set(u) == {"status", "abilities", "k_level"}, "invalid understanding assessment")
    require(u["k_level"] is None or (type(u["k_level"]) is int and 0 <= u["k_level"] <= 4), "invalid contextual K")
    require(type(u["abilities"]) is list, "abilities must be a list")
    seen = set()
    for ability in u["abilities"]:
        require(type(ability) is dict and set(ability) == {"id", "status", "evidence_refs", "rationale"}, "invalid ability assessment")
        require(ability["id"] in ids and ability["id"] not in seen, "unknown/duplicate ability")
        seen.add(ability["id"])
        require(ability["status"] in {"MET", "UNMET", "UNKNOWN"}, "invalid ability status")
        evidence_list(ability["evidence_refs"])
        nonempty(ability["rationale"], "ability rationale")
    if u["status"] == "SUFFICIENT":
        require(seen == ids and all(a["status"] == "MET" for a in u["abilities"]), "SUFFICIENT has unmet required abilities")
    expansion = task["expansion"]
    require(set(expansion) == {"status", "discoveries", "scope_rationale", "evidence_refs"}, "invalid expansion assessment")
    require(type(expansion["discoveries"]) is list, "discoveries must be a list")
    evidence_list(expansion["evidence_refs"])
    seen = set()
    for discovery in expansion["discoveries"]:
        require(type(discovery) is dict and set(discovery) == DISCOVERY_FIELDS, "invalid discovery item")
        require(type(discovery["understanding_gap"]) is str, "discovery must distinguish missing understanding from none")
        for key in ("id", "source_locator", "content", "novelty", "parent_connection"):
            nonempty(discovery[key], "discovery " + key)
        require(discovery["id"] not in seen, "duplicate discovery ID")
        seen.add(discovery["id"])
        require(discovery["observation_kind"] in {"measured", "external_claim", "inference"}, "invalid discovery observation")
        require(discovery["assessment"] in {"MATERIAL", "NONMATERIAL", "UNKNOWN", "UNASSESSED"}, "invalid discovery assessment")
        require(discovery["disposition"] in DISPOSITIONS | {None}, "invalid discovery disposition")
        for p in discovery["target_refs"]:
            ref(p)
        if discovery["disposition"] is not None:
            nonempty(discovery["rationale"], "discovery disposition rationale")
        if discovery["disposition"] in {"CREATE_TASK", "REUSE", "PREREQUISITE", "UPDATE"}:
            require(discovery["target_refs"], "discovery follow-up must actually be registered")
        if discovery["disposition"] == "DEFER":
            nonempty(discovery["reopen_condition"], "deferred discovery requeue condition")
    if expansion["status"] == "ACCOUNTED":
        nonempty(expansion["scope_rationale"], "examined discovery scope")
        require(all(d["assessment"] not in {"UNKNOWN", "UNASSESSED"} or d["disposition"] in
                    {"CREATE_TASK", "PREREQUISITE", "REUSE"} for d in expansion["discoveries"]), "unhandled discovery relevance/materiality")
        require(all(d["disposition"] is not None for d in expansion["discoveries"]), "ACCOUNTED has unhandled discoveries")
    for dep in task["dependency_refs"]:
        require(type(dep) is dict and set(dep) == {"source_ref", "role", "required", "scope", "rationale"}, "invalid role dependency")
        ref(dep["source_ref"])
        require(dep["role"] in ROLES and type(dep["required"]) is bool, "invalid dependency role/requirement")
        nonempty(dep["scope"], "dependency scope"); nonempty(dep["rationale"], "dependency rationale")
    require(task["work_state"] in {"READY", "RUNNING", "WAITING", "PAUSED", "IDLE"}, "invalid learning work state")
    require(task["disposition"] in {"OPEN", "CLOSED", "DEFERRED", "MERGED"}, "invalid learning disposition")
    require(type(task["closure_assessment"]) is dict and type(task["reopen_conditions"]) is list, "invalid closure/reopen record")


def validate_state(task, resolve, previous=None, goal=None, discovery_resolve=None):
    """Check content bindings, closure prerequisites, merge and reopening."""
    if goal:
        facets = {f["id"] for f in goal["extensions"]["goal_alignment"]["facets"]}
        require(task["goal_ref"] == reference(goal), "learning task uses an old goal")
        for c in task["goal_connections"]:
            require(c["goal_ref"] == task["goal_ref"] and set(c["facet_ids"]) <= facets, "learning path lost source goal facets")
    for claim in task["answer"]["claims"]:
        if task["answer"]["status"] == "SUPPORTED":
            require(verified(claim["evidence_refs"], resolve), "SUPPORTED needs current claim evidence")
    if task["answer"]["status"] == "SUPPORTED":
        require(task["answer"]["claims"], "SUPPORTED needs actual answer claims")
    if task["understanding"]["status"] == "SUFFICIENT":
        require(all(verified(a["evidence_refs"], resolve) for a in task["understanding"]["abilities"]), "SUFFICIENT needs ability-specific evidence")
    a = task["assessment"]
    handled_counters = [c["counter_ref"] for c in task["answer"].get("counterevidence_assessments", [])
        if c["disposition"] != "UNRESOLVED" and verified(c["evidence_refs"], resolve)]
    unresolved_counters = [c for c in task["answer"]["counterevidence_refs"] if c not in handled_counters]
    if a["relevance"] == "NOT_RELEVANT" or a["materiality"] == "NONMATERIAL":
        require(verified(a["evidence_refs"], resolve), "minor/irrelevant judgment needs grounded impact assessment")
    for discovery in task["expansion"]["discoveries"]:
        # Discovery registration is history, not a frozen proof dependency.
        # Callers may project target identities to current canonical objects;
        # required proof dependencies below still resolve exact revisions.
        targets = [(discovery_resolve or resolve)(p) for p in discovery["target_refs"]]
        if discovery["disposition"] in {"CREATE_TASK", "PREREQUISITE", "REUSE"}:
            require(targets and all(t["type"] == "LearningTask" for t in targets),
                    f"discovery continuation/reuse needs canonical tasks: {task['id']}/{discovery['id']} "
                    f"target_refs for {discovery['disposition']} require LearningTask; got "
                    f"{[t['id'] + ':' + t['type'] for t in targets]}. Keep consumer effects in processing/propagation records.")
        if discovery["disposition"] == "PREREQUISITE":
            require(all(any(d["source_ref"] == reference(t) and d["required"] and d["role"] in PROOF_ROLES
                            for d in task["dependency_refs"]) for t in targets), "prerequisite discovery lacks actual required dependency")
        if discovery["disposition"] == "UPDATE" and discovery["understanding_gap"].strip():
            require(any(t["type"] == "LearningTask" and t["disposition"] in {"OPEN", "DEFERRED"}
                        for t in targets), "object UPDATE cannot hide an unresolved learning gap")
    if previous and previous["answer_requirements"] != task["answer_requirements"]:
        change = task.get("extensions", {}).get("requirements_change", {})
        require(change.get("rationale") and verified(change.get("evidence_refs", []), resolve),
                "changed ability criteria need observed grounds; never lower them for a pass")
    closure = task["closure_assessment"]
    disposition = task["disposition"]
    if disposition != "OPEN" or task["work_state"] == "PAUSED":
        require({"verdict", "rationale", "evidence_refs", "basis", "scope", "remaining_uncertainties"} <= set(closure), "closure/pause needs bounded assessment")
        nonempty(closure["rationale"], "closure rationale"); nonempty(closure["scope"], "closure scope")
        require(closure["basis"] == basis(task), "closure assessment uses a stale snapshot")
        require(verified(closure["evidence_refs"], resolve), "closure/pause needs observed grounds")
    if disposition == "CLOSED":
        require(task["work_state"] == "IDLE", "closed learning must leave execution frontier")
        require(closure["verdict"] in {"ANSWERED", "NOT_APPLICABLE", "SUPERSEDED", "REUSED"}, "PATH_END/pause is not question closure")
        if closure["verdict"] == "ANSWERED":
            require(a["relevance"] != "UNASSESSED" and a["materiality"] != "UNKNOWN",
                    "ANSWERED retains an unassessed role/materiality scoping obligation")
            require(task["answer"]["status"] == "SUPPORTED" and task["understanding"]["status"] == "SUFFICIENT", "ANSWERED needs supported answer and sufficient abilities")
            require(not task["answer"]["gaps"] and not unresolved_counters, "ANSWERED retains unresolved validity gaps/counterevidence")
            require(task["expansion"]["status"] == "ACCOUNTED", "ANSWERED has unassessed discovery space")
        elif closure["verdict"] in {"REUSED", "SUPERSEDED"}:
            require(closure.get("target_ref"), "reuse/supersession needs target task")
            target = resolve(closure["target_ref"])
            require(target["type"] == "LearningTask" and target["id"] != task["id"] and target["disposition"] == "CLOSED", "reuse target must be independently closed")
            require(closure.get("compatibility") and closure.get("preserved_connections") == task["goal_connections"], "reuse must preserve scope compatibility and parent obligations")
        for dep in task["dependency_refs"]:
            if dep["required"] and dep["role"] != "DISCOVERED_FROM":
                source = resolve(dep["source_ref"])
                require(source["type"] != "LearningTask" or source["disposition"] == "CLOSED", "closed task retains a critical unfinished dependency")
    elif disposition == "MERGED":
        require(task["work_state"] == "IDLE" and closure["verdict"] == "REUSED", "merged task must leave frontier with reuse assessment")
        target = resolve(closure.get("target_ref", {}))
        require(target["type"] == "LearningTask" and target["id"] != task["id"] and target["disposition"] != "MERGED", "invalid merge target/cycle")
        require(closure.get("compatibility") and all(c in target["goal_connections"] for c in task["goal_connections"]), "merge drops goal/parent connections")
        require(all(d in target["dependency_refs"] for d in task["dependency_refs"]) and all(c in target["reopen_conditions"] for c in task["reopen_conditions"]), "merge drops dependency/reopen obligations")
        require(all(d in target["expansion"]["discoveries"] for d in task["expansion"]["discoveries"]), "merge drops discovered follow-up obligations")
    elif disposition == "DEFERRED" or task["work_state"] == "PAUSED":
        require(task["reopen_conditions"] and closure.get("impact") and closure.get("remaining_work"), "deferral/pause needs impact, remaining work and requeue conditions")
        if task["work_state"] == "PAUSED":
            require(disposition == "OPEN" and closure["verdict"] == "CONSTRAINT", "constraint pause must not imply question answered")
        elif disposition == "DEFERRED":
            require(closure.get("selected_action") in ACTIONS and closure.get("comparison_rationale"),
                    "deferral needs selected competing action and grounded comparison")
    if previous and previous["disposition"] in {"CLOSED", "MERGED"} and disposition == "OPEN":
        event = task.get("extensions", {}).get("reopen_event", {})
        require(event.get("kind") in REOPEN and event.get("rationale"), "closed task needs a material reopening condition")
        require(verified(event.get("evidence_refs", []), resolve), "reopening needs observed material evidence")
        require(semantic_content(previous) != semantic_content(task), "paraphrase/bookkeeping cannot reopen a closed task")
        require(event.get("kind") in {"CONTEXT_CHANGED", "SCOPE_CHANGED"} or any(
            p not in list(_all_evidence(previous)) for p in event["evidence_refs"]), "unchanged evidence cannot reopen learning")
    if (disposition == "OPEN" and task["work_state"] != "PAUSED" and task["answer"]["status"] == "SUPPORTED"
        and task["understanding"]["status"] == "SUFFICIENT" and task["expansion"]["status"] == "ACCOUNTED"
        and not task["answer"]["gaps"] and not unresolved_counters):
        unfinished = any(d["required"] and d["role"] != "DISCOVERED_FROM"
            and resolve(d["source_ref"])["type"] == "LearningTask"
            and resolve(d["source_ref"])["disposition"] != "CLOSED" for d in task["dependency_refs"])
        require(unfinished, "sufficient learning must end this unit and return upward")


def _all_evidence(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_refs":
                yield from child
            else:
                yield from _all_evidence(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_evidence(child)


def task_records(documents):
    return [d for d in documents if d["type"] == "LearningTask"]


def important_task(task):
    a = task["assessment"]
    return (a["relevance"] != "NOT_RELEVANT" and a["materiality"] != "NONMATERIAL")


def frontier(documents, obligations=()):
    tasks = task_records(documents)
    pending_targets = {o["target_ref"]["id"] for o in obligations if o["status"] == "PENDING"}
    ready, waiting, stopped, paused = [], [], [], []
    by_id = {d["id"]: d for d in documents}
    for task in tasks:
        item = {"task_ref": reference(task), "question": task["question"], "work_state": task["work_state"],
                "disposition": task["disposition"], "important": important_task(task),
                "next_action": task.get("extensions", {}).get("next_action"),
                "answer_state": task["answer"]["status"], "understanding_state": task["understanding"]["status"],
                "expansion_state": task["expansion"]["status"]}
        item["pending_upward_assessment"] = task["id"] in pending_targets
        blocked = any(d["required"] and d["role"] != "DISCOVERED_FROM"
            and (by_id.get(d["source_ref"]["id"], {}).get("validity_status") != "VALID" or
                 (by_id.get(d["source_ref"]["id"], {}).get("type") == "LearningTask" and
                  by_id[d["source_ref"]["id"]]["disposition"] != "CLOSED")) for d in task["dependency_refs"])
        if task["disposition"] in {"CLOSED", "MERGED"}:
            stopped.append(item)
        elif task["work_state"] == "PAUSED" or task["disposition"] == "DEFERRED":
            paused.append(item)
        elif blocked:
            waiting.append(item)
        elif task["validity_status"] == "VALID":
            ready.append(item)
    return {"ready": ready, "waiting": waiting, "paused_or_deferred": paused, "ended": stopped}


def learning_gate(candidate, documents, obligations, resolve):
    errors = []
    current = {d["id"]: d for d in documents}
    for task in task_records(documents):
        a = task["assessment"]
        relevant = a["role"] in {"CRITICAL", "SELECTION", "SCOPING"}
        if relevant and important_task(task):
            if task["validity_status"] != "VALID" or task["disposition"] != "CLOSED":
                errors.append("important unfinished learning task: " + task["id"])
            else:
                try:
                    validate_state(task, resolve,
                        discovery_resolve=lambda p: resolve(reference(current[p["id"]])))
                except ValueError as exc:
                    errors.append(str(exc))
    for o in obligations:
        if o["status"] == "PENDING":
            target = next((d for d in documents if d["id"] == o["target_ref"]["id"]), None)
            if target is None or target["type"] != "LearningTask" or important_task(target):
                errors.append("pending upward propagation: " + o["id"])
    return errors
