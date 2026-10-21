"""Transactional, optimistic, versioned state. No host model or tool execution."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .files import file_sha256, validate_artifacts
from .schema import (ACTIONS, MANAGEMENT, CONTRACT_VERSION, SCHEMA_VERSION,
                     FIELDS, META, REVIEW_CHECKS, REFRAME_TRIGGERS, TERMINAL, STORAGE_VERSION, ContractError,
                     require, references, same_references, ref, validate, validate_decision,
                     candidate_patch, validate_result_shape, validate_completion, validate_discovery_ids, TRANSITIONS)
from .graph import reference, verified, evaluate, check_io, predicate
from .deliberation import (validate_alignment, validate_links, question_records,
                           review_errors, review_inputs, review_subject_errors, requirements_context, feedback, questions)
from .learning import (validate_state as validate_learning, dependencies, semantic_content,
                       frontier, learning_gate, important_task, validate_plan, consumption_link_errors, ROLES, PROOF_ROLES)
from . import tool_obligations, goal_interpretation


def now():
    return datetime.now(timezone.utc).isoformat()


def _validate_evidence_time(doc):
    # §12.2/13.3: a completed observation cannot follow its new stored record.
    # Unqualified/unknown times keep their existing representation; this does
    # not establish the claim's truth or replace the host's time/scope judgment.
    try:
        observed = datetime.fromisoformat(doc["observed_at"])
    except ValueError:
        return
    if observed.tzinfo is not None:
        require(observed <= datetime.fromisoformat(doc["updated_at"]),
                "observed_at is later than the core-owned record updated_at")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def contract_digest():
    root = Path(__file__).resolve().parents[2]
    files = [root / "SKILL.md"] + sorted((root / "references").rglob("*.md"))
    return digest({str(p.relative_to(root)): p.read_text() for p in files})


def implementation_digest():
    root = Path(__file__).resolve().parents[2]
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob("*")) if p.is_file()
                   and "__pycache__" not in p.parts and p.suffix in {".py", ".md", ".yaml"}})


def important(items):
    return any(not isinstance(item, dict) or item.get("important", True) for item in items)


def active_reference_body(doc):
    # Lineage and discovery catalogs are history, not proof dependencies.
    body = {k: v for k, v in doc.items() if k not in META | {"parent_refs"}}
    if doc["type"] == "LearningTask":
        body.pop("origin_refs", None); body.pop("goal_connections", None)
        body.pop("closure_assessment", None); body.pop("expansion", None)
        body["dependency_refs"] = [d for d in doc["dependency_refs"] if d["role"] != "DISCOVERED_FROM"]
    if doc["type"] == "Frame":
        body.pop("information_requirements", None)
    if doc["type"] == "KnowledgeAsset":
        body["understanding"] = [{k:v for k,v in u.items() if k != "questions"} for u in doc["understanding"]]
    if "extensions" in body:
        body["extensions"] = {k:v for k,v in body["extensions"].items() if k not in {"questions", "reopen_event", "legacy_origin"}}
    return body | {"provenance": doc["provenance"]}


def active_references(doc):
    return references(active_reference_body(doc))


class Core:
    def __init__(self, state_path):
        self.path = Path(state_path).expanduser().resolve()
        skill_root = Path(__file__).resolve().parents[2]
        require(self.path != skill_root and skill_root not in self.path.parents,
                "state must be outside the installed skill")
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path / "state.sqlite3"), isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entities (
                run_id TEXT NOT NULL REFERENCES runs(id), id TEXT NOT NULL,
                revision INTEGER NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (run_id,id,revision));
            CREATE TABLE IF NOT EXISTS operations (
                run_id TEXT NOT NULL REFERENCES runs(id), id TEXT NOT NULL,
                idem TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (run_id,id), UNIQUE (run_id,idem));
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL,
                data TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(run_id,revision));
        """)
        row = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if row:
            if row[0] != str(STORAGE_VERSION):
                self.db.close()
                raise ContractError("database schema mismatch; verified migration required")
        else:
            self.db.execute("INSERT INTO metadata VALUES ('schema_version',?)", (str(STORAGE_VERSION),))

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self, *, rollback=False):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("ROLLBACK" if rollback else "COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _event(self, run_id, kind, data):
        self.db.execute("INSERT INTO events(run_id,at,kind,data) VALUES(?,?,?,?)", (run_id, now(), kind, encode(data)))

    def _run(self, run_id, compatible=True):
        row = self.db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        require(row is not None, "unknown run_id")
        run = json.loads(row[0])
        if compatible:
            require(run["schema_version"] == SCHEMA_VERSION and run["contract_version"] == CONTRACT_VERSION
                    and run["contract_digest"] == contract_digest()
                    and run.get("extensions", {}).get("implementation_digest") == implementation_digest(),
                    "contract/schema mismatch (including executable package identity); inspect status and use a verified migration or a new linked run")
        return run

    def _save_entity(self, run_id, doc):
        validate(doc)
        self.db.execute("INSERT INTO entities VALUES (?,?,?,?)", (run_id, doc["id"], doc["revision"], encode(doc)))

    def _save_run(self, run):
        run["updated_at"] = now()
        self.db.execute("UPDATE runs SET data=? WHERE id=?", (encode(run), run["id"]))
        self._save_entity(run["id"], run)

    def _meta(self, run_id, identity, kind, previous=None, provenance=None, validity="VALID"):
        timestamp = now()
        return {"id": identity, "type": kind, "schema_version": SCHEMA_VERSION,
                "created_at": previous["created_at"] if previous else timestamp,
                "updated_at": timestamp, "source_run_id": run_id,
                "revision": previous["revision"] + 1 if previous else 1,
                "provenance": provenance or [], "validity_status": validity}

    def documents(self, run_id):
        rows = self.db.execute("""SELECT e.data FROM entities e JOIN
            (SELECT id,MAX(revision) AS rev FROM entities WHERE run_id=? GROUP BY id) latest
            ON e.id=latest.id AND e.revision=latest.rev WHERE e.run_id=? ORDER BY e.id""", (run_id, run_id))
        return [json.loads(row[0]) for row in rows]

    def get(self, run_id, identity, revision=None):
        if revision is None:
            row = self.db.execute("SELECT data FROM entities WHERE run_id=? AND id=? ORDER BY revision DESC LIMIT 1", (run_id, identity)).fetchone()
        else:
            row = self.db.execute("SELECT data FROM entities WHERE run_id=? AND id=? AND revision=?", (run_id, identity, revision)).fetchone()
        require(row is not None, f"missing entity {identity}@{revision}")
        return json.loads(row[0])

    def resolve(self, run_id, pointer, valid=True):
        ref(pointer)
        doc = self.get(run_id, pointer["id"], pointer["revision"])
        current = self.get(run_id, pointer["id"])
        if valid:
            self._require_current_ref(pointer, current)
        return doc

    @staticmethod
    def _require_current_ref(pointer, current):
        """Reject a stale binding with observed versions, never refresh it."""
        if current['revision'] != pointer['revision'] or current['validity_status'] != 'VALID':
            raise ContractError(f'stale reference {pointer}', details={
                'requested_ref':dict(pointer), 'current_ref':reference(current),
                'current_validity_status':current['validity_status']})

    @contextmanager
    def _read_view(self, run_id):
        """Share only one readonly query's coherent current documents and exact refs.

        No view survives this call or any write; package identity is still checked
        by the original _run boundaries. Historical/stale lookups keep resolve.
        """
        own_transaction = not self.db.in_transaction
        if own_transaction:
            self.db.execute('BEGIN')
        try:
            documents = self.documents(run_id)
            current = {d['id']:d for d in documents}
            def resolve(pointer):
                ref(pointer)
                document = current.get(pointer['id'])
                if document is not None and document['revision'] == pointer['revision']:
                    self._require_current_ref(pointer, document)
                    return document
                return self.resolve(run_id,pointer)
            yield documents,resolve
        finally:
            if own_transaction:
                self.db.execute('ROLLBACK')

    def _check_refs(self, run_id, doc, lookup=None):
        lookup = lookup or (lambda r: self.resolve(run_id, r))
        for pointer in active_references(doc):
            lookup(pointer)
        # Questions are immutable owner links with a current canonical task projection.
        for _, pointer in questions(doc):
            try:
                target = lookup(pointer)
            except ContractError:
                target = self.resolve(run_id, pointer, valid=False)
            require(target["type"] == "LearningTask", "question ref must point to LearningTask")
        if doc["type"] == "LearningTask":
            for pointer in doc["origin_refs"]:
                try:
                    lookup(pointer)
                except ContractError:
                    self.resolve(run_id, pointer, valid=False)
        for pointer in doc.get("parent_refs", []):
            try:
                parent = lookup(pointer)
            except ContractError:
                parent = self.resolve(run_id, pointer, valid=False)
            require(parent["type"] == "Frame", "Frame lineage points to non-Frame")
        for key, value in doc.items():
            if key.endswith("evidence_refs"):
                for pointer in value:
                    require(lookup(pointer)["type"] == "EvidenceRecord", "evidence ref points to non-evidence")
        typed_keys = {"goal_ref": "GoalSpec", "candidate_ref": "SolutionCandidate", "review_ref": "ReviewRecord"}
        for key, kind in typed_keys.items():
            if key in doc:
                require(lookup(doc[key])["type"] == kind, f"wrong {key} type")
        for key, kind in {"frame_refs": "Frame", "asset_refs": "KnowledgeAsset",
                          "capability_refs": "Capability", "provided_capability_refs": "Capability",
                          "validation_refs": "EvidenceRecord"}.items():
            for index, pointer in enumerate(doc.get(key, [])):
                actual = lookup(pointer)["type"]
                if actual != kind:
                    raise ContractError(f"wrong {key} type", details={
                        'path':f"{doc['id']}.{key}[{index}]",'expected_type':kind,'actual_type':actual})

    def _checkpoint(self, run):
        documents = self.documents(run["id"])
        pending = [json.loads(row[0]) for row in self.db.execute("SELECT data FROM operations WHERE run_id=?", (run["id"],))]
        snapshot = {"run": run, "documents": documents,
                    "operations": pending, "state_path": str(self.path)}
        checksum = digest(snapshot)
        self.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (run["id"], run["revision"], encode(snapshot), checksum))
        record = {**self._meta(run["id"], "checkpoint-" + str(run["revision"]), "Checkpoint"),
                  "state_revision": run["revision"],
                  "pending_operations": [reference(o) for o in pending if (not o["applied"] or o["result"].get("outcome") == "UNKNOWN") and not o["extensions"].get("resolved")],
                  "file_refs": [], "snapshot_digest": checksum}
        self._save_entity(run["id"], record)
        return checksum

    def create(self, goal, environment=None, resources=None, parent_run_id=None):
        guidance = ('HostIO.start(goal, parent_run=None) and solve --input take the raw GoalSpec. '
                    'For explicit environment/resources, use separate JSON file path options through '
                    'solve --environment/--resources or the environment/resources options of '
                    'HostIO.call("solve", payload=goal). '
                    'See schema --entity GoalSpec; do not move a request envelope into extensions.')
        if not isinstance(goal, dict):
            raise ContractError('solve input requires a raw GoalSpec object', details={
                'path': 'solve.input', 'expected_type': 'GoalSpec object', 'guidance': guidance})
        envelope_keys = sorted(set(goal) & {'goal', 'environment', 'resources'})
        if envelope_keys:
            raise ContractError('solve input requires a raw GoalSpec object; request envelopes are unsupported',
                details={'path': 'solve.input', 'expected_type': 'GoalSpec object',
                         'unexpected_keys': envelope_keys, 'guidance': guidance})
        run_id = "run-" + uuid.uuid4().hex
        with self.transaction():
            require(not (set(goal) & (META - {"id", "type", "provenance"})), "initial metadata is core-owned")
            compiled = {**goal, **self._meta(run_id, goal.get("id", "goal"), "GoalSpec",
                                           provenance=goal.get("provenance", []))}
            validate(compiled)
            validate_alignment(compiled)
            # Initial goal can cite source text/locators, not imaginary entity refs.
            require(not list(references(compiled)), "initial GoalSpec references must be registered after run creation")
            run = {**self._meta(run_id, run_id, "ReasoningRun"), "goal_ref": reference(compiled),
                   "state": "CREATED", "contract_version": CONTRACT_VERSION,
                   "contract_digest": contract_digest(), "environment": environment or {},
                   "resource_observations": resources or {"remaining_tokens": None, "remaining_cost": None},
                   "state_path": str(self.path), "extensions": {"parent_run_id": parent_run_id,
                                                               "implementation_digest": implementation_digest()}}
            self.db.execute("INSERT INTO runs VALUES(?,?)", (run_id, encode(run)))
            self._save_entity(run_id, compiled)
            for scope in (tool_obligations.seed(compiled, 'scope'), goal_interpretation.seed(compiled)):
                self._save_entity(run_id, {**scope, **self._meta(run_id, scope['id'], 'LearningTask')})
            self._save_entity(run_id, run)
            self._event(run_id, "CREATED", {"goal_ref": reference(compiled), "source_request": compiled["source_request"]})
            self._checkpoint(run)
        return run

    def _expected(self, run, expected_revision):
        require(type(expected_revision) is int and run["revision"] == expected_revision,
                f"state revision conflict: current {run['revision']}, observed {expected_revision}")

    def begin(self, run_id, request):
        try:
            return self._begin(run_id, request)
        except ContractError as exc:
            # A rejected Commit is observable history, not a successful operation.
            if self.db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
                with self.transaction():
                    self._event(run_id, "REJECTED_INTENT", {"action": request.get("action"), "reason": str(exc)})
            raise

    def _begin(self, run_id, request):
        """Save intent and concise DDC before host reasoning/tool execution."""
        with self.transaction():
            run = self._run(run_id)
            key = request.get("idempotency_key")
            require(type(key) is str and key, "intent requires idempotency_key")
            fingerprint = digest(request)
            old = self.db.execute("SELECT data FROM operations WHERE run_id=? AND idem=?", (run_id, key)).fetchone()
            if old:
                op = json.loads(old[0])
                require(op["extensions"]["request_digest"] == fingerprint, "idempotency key reused with different intent")
                return op
            self._expected(run, request.get("observed_revision"))
            require(run["state"] == "ACTIVE" or (request.get("action") == "RECOVERY_INSPECT" and run["state"] in {"SUSPENDED", "BLOCKED"}), "intent requires ACTIVE run, except explicit recovery inspection")
            require(set(request) == {"action", "observed_revision", "input_refs", "constraints", "evidence_refs",
                                     "decision", "intent", "idempotency_key"}, "invalid operation input fields")
            require(type(request["input_refs"]) is list and type(request["evidence_refs"]) is list
                    and type(request["constraints"]) is list and type(request["intent"]) is dict, "invalid operation input types")
            for pointer in request["input_refs"] + request["evidence_refs"]:
                self.resolve(run_id, pointer)
            for pointer in references(request["intent"]):
                self.resolve(run_id, pointer)
            for pointer in request["evidence_refs"]:
                require(self.resolve(run_id, pointer)["type"] == "EvidenceRecord", "operation evidence must be EvidenceRecord")
            decision = request["decision"]
            validate_decision(decision)
            observation = decision["ddc"]["observable_state"]
            current = self.observe(run_id)
            require(type(observation) is dict and observation.get("state_digest") == current["state_digest"]
                    and observation.get("revision") == run["revision"]
                    and type(observation.get("facts")) is list and observation["facts"],
                    "DDC must cite fresh observe revision/digest and actual host-observed facts")
            require(decision["action"] == request["action"], "decision/operation action mismatch")
            if request["action"] in {"DISCOVER_KNOWLEDGE", "DEEPEN_KNOWLEDGE"}:
                require(request["intent"].get("learning_task_refs"), "learning action needs current LearningTask refs")
            rebinding = request['intent'].get('interpretation_rebind')
            if rebinding is not None:
                require(request['action'] == 'SIMPLIFY' and type(rebinding) is dict
                    and set(rebinding) == {'task_ref', 'rationale'}
                    and type(rebinding['rationale']) is str and rebinding['rationale'].strip(),
                    'interpretation rebinding needs explicit SIMPLIFY task/rationale')
                task = self.resolve(run_id, rebinding['task_ref'])
                require(task['id'] == goal_interpretation.identity(run['goal_ref']['id'])
                    and task['disposition'] == 'CLOSED' and task['work_state'] == 'IDLE',
                    'interpretation rebinding is only for the closed canonical assessment')
                require(not request['intent'].get('learning_task_refs'),
                    'interpretation rebinding cannot schedule ended learning')
            for pointer in request["intent"].get("learning_task_refs", []):
                task = self.resolve(run_id, pointer)
                require(task["type"] == "LearningTask" and task["disposition"] == "OPEN"
                        and task["work_state"] in {"READY", "RUNNING", "WAITING"},
                        "ended/paused/waiting learning cannot be scheduled; reassess material change first")
                require(reference(task) in [i["task_ref"] for i in current["learning_frontier"]["ready"]],
                        "learning task is waiting for dependency/upward assessment")
            if request["intent"].get("learning_task_refs"):
                plans = request["intent"].get("learning_plan", [])
                require(same_references([p.get("task_ref") for p in plans], request["intent"]["learning_task_refs"]),
                        "learning plan must cover exact selected task refs")
                for plan in plans:
                    require(all(type(plan.get(k)) is str and plan[k].strip() for k in
                        ("parent_role", "gap", "sufficient_when", "failure_alternative")),
                        "learning plan needs role/gap/discriminator/sufficiency/failure alternative")
                    validate_plan(plan, self.resolve(run_id, plan["task_ref"]), lambda p: self.resolve(run_id, p))
            if request["action"] == "REFRAME":
                trigger = request["intent"].get("trigger")
                require(trigger in REFRAME_TRIGGERS, "unsupported Reframe trigger")
                require(request["evidence_refs"], "Reframe needs observable trigger evidence")
            if request["action"] == "COMMIT":
                require({"candidate_ref", "review_ref"} <= set(request["intent"]), "Commit needs candidate/review refs")
                gate = self.commit_gate(run_id, request["intent"]["candidate_ref"], request["intent"]["review_ref"])
                require(gate["passed"], "Commit rejected: " + "; ".join(gate["errors"]))
            if request["action"] == "EXECUTE":
                # §10.4 executes the adopted solution. Pre-adoption observations
                # remain work of the selected reasoning action (§9.1).
                adopted = {key: run["extensions"].get("committed_" + key)
                           for key in ("candidate_ref", "review_ref")}
                require(all(adopted.values()),
                        "EXECUTE needs a current committed candidate and review; "
                        "use a selected reasoning action for pre-adoption observations")
                for field, pointer in adopted.items():
                    require(field not in request["intent"] or request["intent"][field] == pointer,
                            "EXECUTE " + field + " differs from the committed solution")
                gate = self.commit_gate(run_id, adopted["candidate_ref"], adopted["review_ref"])
                require(gate["passed"], "EXECUTE adoption rejected: " + "; ".join(gate["errors"]))
            # Identical failed work cannot be replayed with a fresh key absent evidence.
            work_signature = digest({"action": request["action"], "input_refs": request["input_refs"],
                                     "environment": run["environment"], "intent": {k: v for k, v in request["intent"].items() if k != "retry_evidence_refs"}})
            for row in self.db.execute("SELECT data FROM operations WHERE run_id=?", (run_id,)):
                old_op = json.loads(row[0])
                if old_op["extensions"]["work_signature"] == work_signature and old_op["result"].get("outcome") == "FAILED":
                    grounds = request["intent"].get("retry_evidence_refs", [])
                    require(grounds and verified(grounds, lambda r: self.resolve(run_id, r)), "identical failed work needs new retry evidence")
                    require(any(r not in old_op["extensions"].get("evidence_refs", []) for r in grounds), "retry evidence is unchanged")
            decision_id = "decision-" + uuid.uuid4().hex
            decision_doc = {**decision, **self._meta(run_id, decision_id, "DecisionRecord"),
                            "observed_revision": run["revision"], "result": {}}
            self._check_refs(run_id, decision_doc)
            self._save_entity(run_id, decision_doc)
            op_id = "op-" + uuid.uuid4().hex
            op = {**self._meta(run_id, op_id, "OperationRecord", provenance=[reference(decision_doc)]),
                  "action": request["action"], "input_refs": request["input_refs"], "intent": request["intent"],
                  "attempt": 1, "result": {}, "applied": False, "idempotency_key": key,
                  "extensions": {"request_digest": fingerprint, "work_signature": work_signature,
                                 "evidence_refs": request["evidence_refs"], "constraints": request["constraints"],
                                 "decision_ref": reference(decision_doc), "expected_apply_revision": run["revision"] + 1}}
            self._save_entity(run_id, op)
            self.db.execute("INSERT INTO operations VALUES(?,?,?,?)", (run_id, op_id, key, encode(op)))
            run["revision"] += 1
            self._save_run(run)
            self._event(run_id, "INTENT", {"operation_id": op_id, "action": op["action"], "decision_ref": reference(decision_doc)})
            self._checkpoint(run)
        return op

    def record_observation(self, run_id, op_id, expected_revision, artifacts):
        """Preserve real tool output before semantic assessment (§26.3/27.6.18)."""
        with self.transaction():
            run = self._run(run_id)
            self._expected(run, expected_revision)
            op = self.get(run_id, op_id)
            require(op["type"] == "OperationRecord" and not op["applied"]
                    and not op["extensions"].get("resolved"), "observation requires pending intent")
            self._expected(run, op["extensions"]["expected_apply_revision"])
            require(type(artifacts) is list and artifacts, "observation needs actual artifact records")
            for artifact in artifacts:
                require(type(artifact) is dict and set(artifact) == {"path", "sha256", "source"},
                        "observation artifact needs path/hash/source")
                path = Path(artifact["path"])
                require(path.is_absolute() and path.is_file() and artifact["source"], "observation artifact is absent")
                require(file_sha256(path) == artifact["sha256"],
                        "observation artifact changed")
            saved = op["extensions"].get("actual_observations", [])
            additions = [a for a in artifacts if a not in saved]
            if not additions:
                return op
            updated = {**op, **self._meta(run_id, op_id, "OperationRecord", previous=op, provenance=op["provenance"]),
                "extensions": {**op["extensions"], "actual_observations": saved + additions,
                               "expected_apply_revision": run["revision"] + 1}}
            self._save_entity(run_id, updated)
            self.db.execute("UPDATE operations SET data=? WHERE run_id=? AND id=?", (encode(updated), run_id, op_id))
            run["revision"] += 1
            self._save_run(run)
            self._event(run_id, "OBSERVATION_PRESERVED", {"operation_id": op_id, "artifacts": additions,
                "assessment": "PENDING; no semantic success or sufficiency inferred"})
            self._checkpoint(run)
        return updated

    def _obligations(self, run_id, additions=(), resolutions=()):
        obligations = {}
        saved_resolutions = []
        for row in self.db.execute("SELECT data FROM operations WHERE run_id=? ORDER BY rowid", (run_id,)):
            op = json.loads(row[0])
            for item in op["extensions"].get("propagation_obligations", []):
                obligations[item["id"]] = item
            saved_resolutions.extend(op["extensions"].get("propagation_resolutions", []))
        for item in additions:
            obligations.setdefault(item["id"], item)
        for item in [*saved_resolutions, *resolutions]:
            if item["id"] in obligations:
                obligations[item["id"]] = {**obligations[item["id"]], **item,
                    "status": "PENDING" if item["assessment"] == "NEEDS_OBSERVATION" else "RESOLVED"}
        latest = {}
        for item in obligations.values():
            key = (item["source_ref"]["id"], item["target_ref"]["id"], item["relationship_role"], item["affected_scope"])
            prior = latest.get(key)
            if prior and prior["status"] == "PENDING" and prior["source_ref"]["revision"] < item["source_ref"]["revision"]:
                obligations[prior["id"]] = {**prior, "status": "SUPERSEDED", "superseded_by": item["id"]}
                item = {**item, "inherited_remaining_work": prior["remaining_work"]}
                obligations[item["id"]] = item
            latest[key] = item
        return list(obligations.values())

    def _derive_obligations(self, run_id, previous, prepared, invalidated):
        docs = {d["id"]: d for d in self.documents(run_id)}
        docs.update(prepared)
        changed = {identity for identity, old in previous.items()
                   if semantic_content(old) != semantic_content(prepared[identity])}
        changed.update(invalidated)
        obligations = []
        for consumer in docs.values():
            for dep in dependencies(consumer):
                source_id = dep["source_ref"]["id"]
                if source_id not in changed or dep["role"] == "DISCOVERED_FROM":
                    continue
                target = dep.get("target_ref", reference(consumer))
                source = docs[source_id]
                change_id = source_id + "@" + str(source["revision"])
                identity = "prop-" + digest([change_id, target["id"], dep["role"], dep["scope"]])[:24]
                obligations.append({"id": identity, "source_ref": reference(source),
                    "source_change_id": change_id, "target_ref": target,
                    "relationship_role": dep["role"], "affected_scope": dep["scope"],
                    "status": "PENDING", "assessment": None, "evidence_refs": [],
                    "rationale": "Declared consumer must assess changed provider in this scope",
                    "result_refs": [], "remaining_work": ["Assess maintain/revise/invalidate/observation"]})
        return obligations

    def _validate_resolutions(self, run_id, resolutions, additions):
        require(type(resolutions) is list, "propagation resolutions must be a list")
        pending = {o["id"]: o for o in self._obligations(run_id, additions)}
        seen = set()
        for item in resolutions:
            require(type(item) is dict and set(item) == {"id", "assessment", "evidence_refs", "rationale", "result_refs", "remaining_work"}, "invalid propagation assessment")
            obligation = pending.get(item["id"])
            if obligation is None or item["id"] in seen or obligation["status"] != "PENDING":
                raise ContractError("unknown/duplicate/already resolved propagation", details={
                    "id":item["id"], "duplicate":item["id"] in seen,
                    "status":obligation["status"] if obligation else "UNKNOWN",
                    "superseded_by":obligation.get("superseded_by") if obligation else None,
                    "hint":"Inspect patch-refs propagation_obligations for this exact proposed change; "
                           "assess the actual successor scope explicitly, never copy an old resolution blindly."})
            seen.add(item["id"])
            require(item["assessment"] in {"MAINTAIN", "REVISE", "INVALIDATE", "NEEDS_OBSERVATION"}, "invalid upward effect")
            require(item["rationale"] and verified(item["evidence_refs"], lambda p: self.resolve(run_id, p)), "upward effect needs grounded scope-specific rationale")
            for pointer in item["result_refs"]:
                self.resolve(run_id, pointer)
            obligation = pending[item["id"]]
            source = self.get(run_id, obligation["source_ref"]["id"])
            require(reference(source) == obligation["source_ref"], "propagation assessment uses a superseded source change")
            if item["assessment"] == "MAINTAIN":
                target = self.get(run_id, obligation["target_ref"]["id"])
                require(target["validity_status"] == "VALID" and reference(target) in item["result_refs"],
                        "MAINTAIN needs the actual current target version")
            if item["assessment"] in {"REVISE", "INVALIDATE"}:
                require(any(p["id"] == obligation["target_ref"]["id"] and p["revision"] > obligation["target_ref"]["revision"]
                            for p in item["result_refs"]), "upward change must actually revise/invalidate target")
            if item["assessment"] == "NEEDS_OBSERVATION":
                require(item["remaining_work"], "pending observation must preserve concrete remaining work")
            else:
                require(not item["remaining_work"], "resolved propagation cannot discard remaining work")
        return resolutions

    @staticmethod
    def _propagation_feedback(obligations):
        return [{"information_need": True, "propagation": True, "key": o["id"],
            "description": o["rationale"], "important": True, "owner_ref": o["target_ref"],
            "status": "PENDING", "next_action": "REVIEW_SOLUTION"}
            for o in obligations if o["status"] == "PENDING"]

    def _validate_learning_operation(self, op, result, prepared, lookup):
        require(type(result["learning_results"]) is list and type(result["path_assessments"]) is list,
                "learning results/path assessments must be lists")
        selected = op["intent"].get("learning_task_refs", [])
        actual = [r.get("task_ref") for r in result["learning_results"]]
        # §21.3: stable identity/version, not presentation order, binds results.
        require(same_references(actual, selected),
                "actual learning output must cover selected task versions")
        for i, record in enumerate(result["learning_results"]):
            require(set(record) == {"task_ref", "result_ref", "answer_refs", "understanding_change",
                "discovery_ids", "upward_effects", "observations", "prediction_difference"}, "learning needs four actual result bundles")
            task = lookup(record["result_ref"])
            require(task["type"] == "LearningTask" and task["id"] == record["task_ref"]["id"]
                    and task["revision"] > record["task_ref"]["revision"], "learning output must update actual selected task")
            require(record["observations"] and record["understanding_change"] and record["upward_effects"]
                    and record["prediction_difference"], "learning result cannot substitute fixed empty feedback")
            validate_discovery_ids(record, task, f'learning_results[{i}].discovery_ids')
            for pointer in record["answer_refs"]:
                require(lookup(pointer)["type"] == "EvidenceRecord", "learning answer binding needs observed evidence")
        for path in result["path_assessments"]:
            require(set(path) == {"id", "task_ref", "verdict", "rationale", "evidence_refs", "next_paths"}, "invalid path assessment")
            require(path["verdict"] == "PATH_END" and path["rationale"] and verified(path["evidence_refs"], lookup), "path end needs actual grounds")
            require(lookup(path["task_ref"])["disposition"] == "OPEN", "ending one path cannot answer its question")

    @staticmethod
    def _invalidation_targets(documents, changed, protected):
        stale, frontier = set(), set(changed)
        while frontier:
            following = set()
            for doc in documents:
                if doc["id"] in protected | set(changed) | stale or doc["validity_status"] != "VALID":
                    continue
                if doc["type"] in {"ReasoningRun", "Checkpoint", "OperationRecord", "LearningTask"}:
                    continue
                if doc["type"] == "DependencyLink" and doc["relation"] in ROLES:
                    continue
                pointers = list(active_references(doc))
                if doc["type"] == "DependencyLink" and doc["relation"] == "OR":
                    pointers = [doc["target_ref"], *doc["evidence_refs"]]
                if any(p["id"] in frontier for p in pointers):
                    following.add(doc["id"])
            stale.update(following)
            frontier = following
        return sorted(stale)

    def _invalidated_document(self, run_id, doc, changed, targets):
        if doc["type"] == "SolutionCandidate":
            proof_doc = {**doc, "extensions": {k:v for k,v in doc.get("extensions", {}).items()
                if k != "judgment_dependencies"}}
            functional = {p["id"] for p in active_references(proof_doc)}
            if not functional & (set(changed) | set(targets)):
                return {**doc, **self._meta(run_id, doc['id'], doc['type'], previous=doc,
                    provenance=doc['provenance']), "extensions": {**doc.get("extensions", {}),
                        "selection_validity": "STALE"}}
        return {**doc, **self._meta(run_id, doc['id'], doc['type'], previous=doc,
            provenance=doc['provenance'], validity='STALE')}

    def _invalidate(self, run_id, changed, protected):
        targets = self._invalidation_targets(self.documents(run_id), changed, protected)
        for identity in targets:
            doc = self.get(run_id, identity)
            self._save_entity(run_id, self._invalidated_document(run_id, doc, changed, targets))
        return targets

    def apply(self, run_id, op_id, result, *, validate_only=False):
        """Atomic validation, application, invalidation and checkpoint."""
        with self.transaction(rollback=validate_only):
            run = self._run(run_id)
            row = self.db.execute("SELECT data FROM operations WHERE run_id=? AND id=?", (run_id, op_id)).fetchone()
            require(row is not None, "unknown operation")
            op = json.loads(row[0])
            validate_result_shape(result)
            require(result["operation_id"] == op_id, "wrong operation output id")
            require(result["outcome"] in {"SUCCEEDED", "FAILED", "UNKNOWN"}, "invalid operation outcome")
            checksum = digest(result)
            if op["applied"]:
                require(op["extensions"]["result_digest"] == checksum, "operation already applied with a different result")
                return {"applied": False, "duplicate": True, "revision": run["revision"], "operation": op}
            require(not op["extensions"].get("resolved"), "operation has been reconciled; start a new grounded intent")
            require(run["state"] == "ACTIVE" or (op["action"] == "RECOVERY_INSPECT" and run["state"] in {"SUSPENDED", "BLOCKED"}), "apply requires ACTIVE run, except explicit recovery inspection")
            self._expected(run, op["extensions"]["expected_apply_revision"])
            for pointer in op["input_refs"] + op["extensions"]["evidence_refs"]:
                self.resolve(run_id, pointer)
            for key in {"result_refs", "proposed_state_changes", "evidence_refs", "unresolved_items", "observed_effects", "next_decision_inputs"}:
                require(type(result[key]) is list, f"result {key} must be list")
            changes = result["proposed_state_changes"]
            prepared, previous = {}, {}
            for change in changes:
                change = candidate_patch(change)
                require(type(change) is dict and type(change.get("id")) is str and "type" in change, "change needs id/type")
                identity = change["id"]
                require(identity not in prepared, "duplicate entity in patch")
                require(change["type"] not in {"ReasoningRun", "Checkpoint", "OperationRecord", "DecisionRecord"}, "reserved generated entity")
                require(not (set(change) & (META - {"id", "type", "provenance", "validity_status"})), "metadata is core-owned")
                row = self.db.execute("SELECT data FROM entities WHERE run_id=? AND id=? ORDER BY revision DESC LIMIT 1", (run_id, identity)).fetchone()
                old = json.loads(row[0]) if row else None
                if old:
                    require(old["type"] == change["type"], "entity type cannot change")
                    previous[identity] = old
                if change["type"] == "GoalSpec":
                    require(op["action"] == "GOAL_COMPILE", "goal changes require Goal Compiler")
                    correction = op["intent"].get("source_preservation_correction")
                    require(op["intent"].get("user_change_source") or
                            (type(correction) is str and correction.strip() and old is not None
                             and change.get("source_request") == old["source_request"]
                             and change.get("explicit_constraints") == old["explicit_constraints"]),
                            "goal revision needs explicit user change source or grounded source-preservation correction")
                doc = {**change, **self._meta(run_id, identity, change["type"], previous=old,
                                            provenance=change.get("provenance", []),
                                            validity=change.get("validity_status", "VALID"))}
                try:
                    validate(doc)
                    if doc["type"] == "EvidenceRecord":
                        _validate_evidence_time(doc)
                except ContractError as exc:
                    raise ContractError(f"{identity} ({change['type']}): {exc}") from exc
                if op["action"] == "RECOVERY_INSPECT":
                    require(doc["type"] == "EvidenceRecord" and doc["observation_kind"] == "measured", "recovery inspection may only record direct observations")
                prepared[identity] = doc

            def lookup(pointer):
                ref(pointer)
                if pointer["id"] in prepared:
                    d = prepared[pointer["id"]]
                    require(d["revision"] == pointer["revision"] and d["validity_status"] == "VALID",
                            f"patch reference uses wrong new revision: {pointer}; proposed {reference(d)} ({d['validity_status']})")
                    return d
                return self.resolve(run_id, pointer)

            current_goal = next((d for d in prepared.values() if d['type'] == 'GoalSpec'),
                                self.resolve(run_id, run['goal_ref']))
            combined = {d['id']: d for d in self.documents(run_id)} | prepared
            for question in tool_obligations.registration_changes(current_goal, combined.values(), lookup):
                prepared[question['id']] = {**question, **self._meta(run_id, question['id'], 'LearningTask')}
            current_operations = [json.loads(row[0]) for row in self.db.execute(
                'SELECT data FROM operations WHERE run_id=?', (run_id,))]
            current_operations = [o for o in current_operations if o['id'] != op_id] + [
                {**op, 'applied': True, 'result': result}]
            rebinding = op['intent'].get('interpretation_rebind')
            if rebinding is not None:
                pointer = rebinding['task_ref']
                require(pointer['id'] in previous and pointer['id'] in prepared
                    and reference(previous[pointer['id']]) == pointer,
                    'interpretation rebinding requires the exact prior closed revision')
                task = prepared[pointer['id']]
                goal_interpretation.validate_rebinding(previous[pointer['id']], task)
                require(reference(task) in result['result_refs']
                    and goal_interpretation._fresh_consumption(task, current_operations[-1], current_operations, lookup),
                    'interpretation rebinding needs fresh located current-consumer comparison evidence')
            for doc in prepared.values():
                if doc["type"] == "LearningTask" and doc["validity_status"] == "VALID":
                    validate_learning(doc, lookup, previous.get(doc["id"]),
                        next((d for d in prepared.values() if d["type"] == "GoalSpec"), self.resolve(run_id, run["goal_ref"])),
                        discovery_resolve=lambda p: lookup(reference(prepared[p['id']] if p['id'] in prepared
                            else self.get(run_id, p['id']))))
                    tool_obligations.validate_identity(doc, current_goal, lookup)
                    goal_interpretation.validate_identity(doc, current_goal, lookup)
                    if doc["id"] == goal_interpretation.identity(current_goal["id"]) and doc["disposition"] in {"CLOSED", "MERGED"}:
                        goal_interpretation.observation_binding(goal_interpretation.terminal(doc, lookup), current_operations, lookup)
                    if doc['id'] == tool_obligations.identity(current_goal['id'], 'discovery') and doc['disposition'] in {'CLOSED', 'MERGED'}:
                        actual = tool_obligations.terminal(doc, lookup)
                        require(tool_obligations.observation_binding(actual, current_operations, lookup, raise_on_missing=True),
                                'tool discovery has no preserved actual-search observation binding')
                    if doc['id'] == tool_obligations.identity(current_goal['id'], 'composition') and doc['disposition'] in {'CLOSED', 'MERGED'}:
                        require(tool_obligations.composition_binding(tool_obligations.terminal(doc, lookup), current_operations),
                                'tool composition has no actual current assessment operation')
                self._check_refs(run_id, doc, lookup if doc["validity_status"] == "VALID" else lambda p: self.resolve(run_id, p, valid=False))
                if doc["validity_status"] == "VALID":
                    goal_doc = next((d for d in prepared.values() if d["type"] == "GoalSpec"),
                                    self.resolve(run_id, run["goal_ref"]))
                    if doc["type"] == "GoalSpec":
                        validate_alignment(doc)
                    validate_links(doc, goal_doc)
                if doc["type"] == "Frame" and doc["parent_refs"]:
                    for pointer in doc["parent_refs"]:
                        try:
                            parent = lookup(pointer)
                        except ContractError:
                            parent = self.resolve(run_id, pointer, valid=False)
                        require(parent["type"] == "Frame", "Frame parent is not a Frame")
                        require(any(doc[k] != parent[k] for k in ["object", "representation", "mechanism", "intervention", "information_requirements", "assumptions"]), "reworded title alone does not create a new Frame")
                if doc["type"] == "ReviewRecord":
                    verdict = doc.get("extensions", {}).get("verdict")
                    require(verdict in {"READY", "NEEDS_WORK", "PARTIAL_ONLY", "BLOCKED"}, "Review needs a bounded verdict")
                    if verdict == 'READY':
                        combined = {d['id']: d for d in self.documents(run_id)} | prepared
                        problems = tool_obligations.gate_errors(current_goal, combined.values(), current_operations, lookup)
                        require(not problems, 'Review tool obligations: ' + '; '.join(problems))
                        problems = goal_interpretation.gate_errors(current_goal, combined.values(), current_operations, lookup)
                        require(not problems, 'Review goal interpretation: ' + '; '.join(problems))
                    if verdict == "NEEDS_WORK":
                        followups = doc["extensions"].get("followup_refs", [])
                        require(followups, "NEEDS_WORK must register actual followup work")
                        for pointer in followups:
                            followup = lookup(pointer)
                            require((followup["type"] == "LearningTask" and followup["disposition"] in {"OPEN", "DEFERRED"})
                                    or (followup["type"] == "OperationRecord" and not followup["applied"]
                                        and not followup["extensions"].get("resolved"))
                                    or (followup["type"] == "DependencyLink" and followup["id"] in prepared),
                                    "Review defect needs unfinished learning/operation or an actual dependency update")
            for pointer in result["result_refs"] + result["evidence_refs"]:
                lookup(pointer)
            for pointer in result["evidence_refs"]:
                require(lookup(pointer)["type"] == "EvidenceRecord", "result evidence must be evidence")
            if op["action"] == "REFRAME" and result["outcome"] == "SUCCEEDED":
                frames = [d for d in prepared.values() if d["type"] == "Frame"]
                require(frames, "successful Reframe must produce a Frame")
                stages = op["intent"].get("steps")
                require(type(stages) is dict and set(stages) == {"assumptions", "axis", "structural_difference",
                    "information_requirements", "graph_changes", "dependent_judgments", "validity_changes", "rediscovery_scope"}, "Reframe needs all recorded stages")
            # Persist the actual functional witness as a core-derived dependency
            # projection. Review separately includes selection/goal learning.
            all_docs = {d["id"]: d for d in self.documents(run_id)} | prepared
            consumption_errors = consumption_link_errors(op['intent'].get('learning_plan', []), all_docs.values())
            require(not consumption_errors, '; '.join(consumption_errors))
            for doc in prepared.values():
                if doc["type"] == "SolutionCandidate" and doc["validity_status"] == "VALID":
                    proof = evaluate(doc, list(all_docs.values()), lookup)
                    refs = {i: reference(all_docs[i]) for i in proof["proof_nodes"] if i in all_docs}
                    for identity, sources in proof["proof_links"].items():
                        edge = all_docs[identity]
                        refs[identity] = reference(edge)
                        for pointer in sources + edge["evidence_refs"]:
                            refs[pointer["id"]] = pointer
                    doc.setdefault("extensions", {})["functional_proof_refs"] = sorted(refs.values(), key=lambda p:p["id"])
                    doc["extensions"]["selection_validity"] = "VALID"
            self._validate_learning_operation(op, result, prepared, lookup)
            for doc in prepared.values():
                self._save_entity(run_id, doc)
                if doc["type"] == "GoalSpec":
                    run["goal_ref"] = reference(doc)
            invalidated = self._invalidate(run_id, set(previous), set(prepared))
            new_obligations = self._derive_obligations(run_id, previous, prepared, invalidated)
            resolutions = self._validate_resolutions(run_id, result["propagation_resolutions"], new_obligations)
            pending = self._obligations(run_id, new_obligations, resolutions)
            actual_feedback = feedback(self.documents(run_id)) + self._propagation_feedback(pending)
            require(all(q in result["unresolved_items"] and q in result["next_decision_inputs"]
                        for q in actual_feedback),
                    "saved unresolved information needs must reach unresolved_items and next_decision_inputs; use prepare")
            # Detect a patch that tried to preserve an indirect stale dependency.
            for doc in prepared.values():
                if doc["validity_status"] == "VALID":
                    self._check_refs(run_id, doc)
                if doc["type"] == "ReviewRecord" and doc["validity_status"] == "VALID":
                    require(doc["snapshot"] == self.snapshot(run_id, doc["candidate_ref"]), "Review snapshot does not match exact dependencies")
            gate = None
            if op["action"] == "COMMIT":
                gate = self.commit_gate(run_id, op["intent"]["candidate_ref"], op["intent"]["review_ref"])
                require(gate["passed"], "Commit rejected after result: " + "; ".join(gate["errors"]))
                require(result["outcome"] == "SUCCEEDED", "Commit result cannot pretend unsuccessful adoption")
                run["extensions"]["committed_candidate_ref"] = op["intent"]["candidate_ref"]
                run["extensions"]["committed_review_ref"] = op["intent"]["review_ref"]
            applied_op = {**op, **self._meta(run_id, op_id, "OperationRecord", previous=op, provenance=op["provenance"]),
                          "result": result, "applied": True,
                          "extensions": {**op["extensions"], "result_digest": checksum, "gate": gate,
                                         "actual_feedback": actual_feedback, "propagation_obligations": new_obligations,
                                         "propagation_resolutions": resolutions}}
            self._save_entity(run_id, applied_op)
            self.db.execute("UPDATE operations SET data=? WHERE run_id=? AND id=?", (encode(applied_op), run_id, op_id))
            decision = self.resolve(run_id, op["extensions"]["decision_ref"], valid=False)
            updated_decision = {**decision, **self._meta(run_id, decision["id"], "DecisionRecord", previous=self.get(run_id, decision["id"]), provenance=decision["provenance"]),
                                "result": {"operation_id": op_id, "observed_effects": result["observed_effects"],
                                           "next_decision_inputs": result["next_decision_inputs"],
                                           "unresolved_items": actual_feedback,
                                           "outcome": result["outcome"]}}
            self._save_entity(run_id, updated_decision)
            run["revision"] += 1
            self._save_run(run)
            self._event(run_id, "APPLIED", {"operation_id": op_id, "invalidated": invalidated,
                                           "result_digest": checksum, "outcome": result["outcome"]})
            self._checkpoint(run)
        return {"applied": not validate_only, "duplicate": False, "revision": run["revision"],
                "result_refs": result["result_refs"], "invalidated": invalidated, "gate": gate}

    def preflight(self, run_id, op_id, result):
        """Run the actual prepare/apply checks and roll back every state write.

        No reference repair or semantic judgments are generated. A later apply
        still checks its own current revision/identity; this is not approval.
        """
        prepared = self.prepare(run_id, op_id, result)
        predicted = self.apply(run_id, op_id, prepared, validate_only=True)
        return {'validated': True, 'applied': False, 'prepared_result': prepared,
                'predicted': predicted,
                'scope': 'Deterministic checks only; no semantic approval or reserved revision'}

    def patch_refs(self, run_id, changes):
        """Predict explicit patch versions; never rewrite existing references."""
        with self._read_view(run_id) as (documents, _):
            return self._patch_refs(run_id, changes, documents)

    def _patch_refs(self, run_id, changes, documents):
        run = self._run(run_id)
        require(type(changes) is list, 'patch-refs requires a list of changes')
        current = {d['id']: d for d in documents}
        result = {}
        for change in changes:
            require(type(change) is dict and type(change.get('id')) is str and change['id']
                    and change.get('type') in FIELDS, 'change needs known id/type')
            identity = change['id']
            require(identity not in result, 'duplicate entity in patch')
            require(change['type'] not in {'ReasoningRun', 'Checkpoint', 'OperationRecord', 'DecisionRecord'},
                    'reserved generated entity')
            require(not (set(change) & (META - {'id', 'type', 'provenance', 'validity_status'})),
                    'metadata is core-owned')
            old = current.get(identity)
            require(old is None or old['type'] == change['type'], 'entity type cannot change')
            result[identity] = {'id': identity, 'revision': old['revision'] + 1 if old else 1}
        def bind(value):
            if type(value) is dict:
                if '$patch_ref' in value:
                    require(set(value) == {'$patch_ref'} and type(value['$patch_ref']) is str
                        and value['$patch_ref'] in result, 'patch reference must identify an explicit patch record')
                    return result[value['$patch_ref']]
                return {k:bind(v) for k,v in value.items()}
            return [bind(v) for v in value] if type(value) is list else value
        documents, _, invalidated, additions = self._project_changes(run_id, bind(changes))
        return {'observed_revision': run['revision'], 'refs': result,
                'invalidated_consumers':[{'previous_ref':reference(current[i]),
                    'projected_ref':reference(documents[i]),
                    'projected_validity_status':documents[i]['validity_status'],
                    'selection_validity':documents[i].get('extensions', {}).get('selection_validity')}
                    for i in invalidated],
                'reference_conflicts':self._reference_conflicts(documents.values()),
                'propagation_obligations':self._obligations(run_id, additions),
                'scope': 'Read-only proposed versions and declared dependency effects. No validation, '
                         'semantic approval, automatic rebinding or propagation assessment. Recompute after changing the patch.'}

    @staticmethod
    def _reference_conflicts(documents):
        """Locate active mismatches without refreshing refs or judging their meaning."""
        by_id = {d['id']:d for d in documents}
        conflicts = []
        def located(value, path):
            if type(value) is dict:
                if set(value) == {'id','revision'}:
                    yield path, value
                else:
                    for key, child in value.items():
                        yield from located(child, path + [key])
            elif type(value) is list:
                for index, child in enumerate(value):
                    yield from located(child, path + [index])
        for document in by_id.values():
            if document['type'] in {'Checkpoint', 'DecisionRecord', 'OperationRecord', 'ReasoningRun'}:
                continue
            for path, pointer in located(active_reference_body(document), []):
                target = by_id.get(pointer['id'])
                if target is None or pointer != reference(target) or target['validity_status'] != 'VALID':
                    conflicts.append({'owner_ref':reference(document), 'path':path, 'declared_ref':pointer,
                        'current_ref':reference(target) if target else None,
                        'current_validity_status':target['validity_status'] if target else None})
        return conflicts

    def review_context(self, run_id, candidate_ref):
        """Return the gate's exact subjects without generating Review answers."""
        with self._read_view(run_id) as (documents,resolve):
            return self._review_context(run_id,candidate_ref,documents,resolve)

    def _review_context(self, run_id, candidate_ref, documents, resolve):
        run = self._run(run_id)
        candidate = resolve(candidate_ref)
        require(candidate['type'] == 'SolutionCandidate', 'review-context needs a solution candidate')
        require(candidate['goal_ref'] == run['goal_ref'], 'candidate uses previous goal')
        goal = resolve(run['goal_ref'])
        errors, selected_assets = [], []
        for pointer in candidate['asset_refs']:
            try:
                selected_assets.append(resolve(pointer))
            except ContractError as exc:
                errors.append({'stage':'selected_asset', 'message':str(exc), **exc.details})
        evidence = {}
        for document in [candidate, *selected_assets]:
            for pointer in active_references(document):
                try:
                    record = resolve(pointer)
                except ContractError as exc:
                    errors.append({'stage':'evidence', 'message':str(exc), **exc.details})
                    continue
                if record['type'] == 'EvidenceRecord':
                    evidence[(record['id'], record['revision'])] = record
        # A broken nested binding must not hide the subjects needed to repair it.
        # Gate/snapshot themselves remain strict; no Review snapshot is fabricated.
        try:
            snapshot = self._snapshot(run_id, candidate_ref, documents, resolve)
        except ContractError as exc:
            snapshot = None
            errors.append({'stage':'snapshot', 'message':str(exc), **exc.details})
        try:
            structure = self._candidate_structure(goal, candidate, documents, resolve)
        except ContractError as exc:
            structure = {'errors':[str(exc)], 'reference_error':exc.details}
            errors.append({'stage':'structure', 'message':str(exc), **exc.details})
        return {'observed_revision': run['revision'], 'candidate_ref': candidate_ref,
                'goal_ref': run['goal_ref'], 'snapshot': snapshot,
                'reference_errors':errors, 'reference_conflicts':self._reference_conflicts(documents),
                'structure':structure,
                'selection_context': {'candidate':candidate, 'selected_assets':selected_assets,
                    'evidence':list(evidence.values()),
                    'scope':'Declared records only; no necessity, comparison, recommendation or semantic approval generated'},
                'requirements_context': requirements_context(goal, documents),
                **review_inputs(goal, candidate, documents),
                'scope': 'Current Review inputs only; host supplies each judgment and evidence scope'}

    def snapshot(self, run_id, candidate_ref):
        with self._read_view(run_id) as (documents,resolve):
            return self._snapshot(run_id,candidate_ref,documents,resolve)

    def _snapshot(self, run_id, candidate_ref, docs, resolve):
        candidate = resolve(candidate_ref)
        require(candidate["type"] == "SolutionCandidate", "snapshot needs a solution candidate")
        document_map = {d["id"]: d for d in docs}
        proof = evaluate(candidate, docs, resolve)
        found = {}
        queue = [candidate_ref, self._run(run_id)["goal_ref"]]
        queue += [reference(document_map[i]) for i in proof["proof_nodes"] if i in document_map]
        queue += [reference(document_map[i]) for i in proof["proof_links"]]
        while queue:
            pointer = queue.pop()
            if pointer["id"] in found:
                require(found[pointer["id"]] == pointer, "conflicting dependency revisions")
                continue
            doc = resolve(pointer)
            found[doc["id"]] = pointer
            if doc["type"] == "DependencyLink" and doc["id"] in proof["proof_links"]:
                queue += [doc["target_ref"], *doc["evidence_refs"], *proof["proof_links"][doc["id"]]]
            else:
                queue += list(active_references(doc))
            for _, task_ref in questions(doc):
                task = document_map.get(task_ref['id']) or self.get(run_id, task_ref["id"])
                queue.append(reference(task))
        # Goal/selection learning can invalidate adoption without being selected
        # functional proof. Keep these exact judgment dependencies explicit.
        for task in docs:
            if task["type"] == "LearningTask" and task["assessment"]["role"] in {"CRITICAL", "SELECTION", "SCOPING"}:
                found[task["id"]] = reference(task)
        return sorted(found.values(), key=lambda r: r["id"])

    @staticmethod
    def _candidate_structure(goal, candidate, documents, resolve):
        coverage = evaluate(candidate, documents, resolve)
        errors = []
        for field, label in [('missing','missing mandatory capabilities'),
                ('conflicts','conflicting graph paths'),
                ('ungrounded_assets','assets unavailable or ungrounded')]:
            if coverage[field]:
                errors.append(label + ': ' + ','.join(coverage[field]))
        io_errors = check_io(candidate, resolve)
        return {'coverage':coverage,'io_errors':io_errors,
                'errors':errors + io_errors + review_subject_errors(goal, candidate, documents, resolve),
                'scope':'Declared graph, ports, criterion coverage and contextual assessment presence only; not semantic Review approval'}

    def commit_gate(self, run_id, candidate_ref, review_ref):
        with self._read_view(run_id) as (documents,resolve):
            return self._commit_gate(run_id,candidate_ref,review_ref,documents,resolve)

    def _commit_gate(self, run_id, candidate_ref, review_ref, documents, resolve):
        errors, coverage = [], None
        try:
            run = self._run(run_id)
            candidate = resolve(candidate_ref)
            review = resolve(review_ref)
            require(candidate["type"] == "SolutionCandidate" and review["type"] == "ReviewRecord", "incorrect Commit types")
            require(candidate["goal_ref"] == run["goal_ref"], "candidate uses previous goal")
            require(review["candidate_ref"] == candidate_ref and review["goal_ref"] == run["goal_ref"], "Review covers a different candidate/goal")
            require(review["snapshot"] == self._snapshot(run_id, candidate_ref,documents,resolve), "Review dependencies changed")
            require(not important(review["unresolved_items"]) and not important(candidate["gaps"]), "unresolved mandatory gaps")
            require(candidate["disposition"] == "retain", "candidate is not retained")
            require(candidate.get("extensions", {}).get("selection_validity") == "VALID",
                    "candidate selection/comparison judgment is stale")
            goal = resolve(run["goal_ref"])
            structure = self._candidate_structure(goal, candidate, documents, resolve)
            coverage = structure['coverage']
            errors += structure['errors']
            errors += learning_gate(candidate, documents, self._obligations(run_id), resolve)
            if review.get("extensions", {}).get("verdict") != "READY":
                errors.append("Review is not READY")
            operations = [json.loads(row[0]) for row in self.db.execute(
                'SELECT data FROM operations WHERE run_id=?', (run_id,))]
            errors += tool_obligations.gate_errors(goal, documents, operations, resolve)
            errors += goal_interpretation.gate_errors(goal, documents, operations, resolve)
            errors += review_errors(goal, candidate, review, documents, resolve)
            # §§10.3/25.4/27.7.19: honor every host-declared important
            # condition, including scoped connection/automation checks.
            # Existing checks carry the judgment; no new schema or selector.
            required_checks = set(REVIEW_CHECKS) | set(review["checks"])
            for constraint in goal["explicit_constraints"]:
                required_checks.add("constraint:" + constraint["id"])
                if constraint["predicate"] is not None and predicate(candidate, constraint["predicate"]) is not True:
                    errors.append("explicit constraint fails or unknown: " + constraint["id"])
            for key in required_checks:
                check = review["checks"].get(key)
                if not check or check["status"] != "PASS" or not check["rationale"] or not verified(check["evidence_refs"], resolve):
                    errors.append("missing/failed/ungrounded semantic check: " + key)
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
        return {"passed": not errors, "errors": errors, "coverage": coverage,
                "candidate_ref": candidate_ref, "review_ref": review_ref,
                "semantic_scope": "host judgments with evidence; core verifies structure and versions"}

    def transition(self, run_id, target, expected_revision, reason, evidence_refs=None,
                   verification=None, package_ref=None):
        with self.transaction():
            run = self._run(run_id)
            self._expected(run, expected_revision)
            require(target in TRANSITIONS.get(run["state"], set()), "invalid run state transition; terminal runs require a new linked run")
            require(type(reason) is str and bool(reason.strip()), "transition needs reason")
            grounds = evidence_refs or []
            for pointer in grounds:
                self.resolve(run_id, pointer)
            if target == "ACTIVE" and run["state"] in {"SUSPENDED", "BLOCKED"}:
                require(not self.status(run_id)["pending_operations"], "reconcile pending work before resuming")
                require(verified(grounds, lambda r: self.resolve(run_id, r)), "resume needs resolved-cause evidence")
            if target == "COMPLETED":
                require(not self.status(run_id)["pending_operations"], "pending external effects prevent completion")
                require(not important([i for i in self.status(run_id)["unresolved_items"]
                        if type(i) is not dict or i.get("information_need") is not True]),
                        "current important host conditions prevent completion")
            if target == "BLOCKED":
                require(verified(grounds, lambda r: self.resolve(run_id, r)), "BLOCKED needs observed external condition and alternative investigation evidence")
            if target == "COMPLETED":
                require(package_ref is not None, "completion needs a solution package")
                package = self.resolve(run_id, package_ref)
                require(package["type"] == "SolutionPackage", "invalid solution package")
                committed = run["extensions"].get("committed_candidate_ref")
                require(committed == package["candidate_ref"], "solution was not committed")
                gate = self.commit_gate(run_id, committed, package["review_ref"])
                require(gate["passed"], "completion Commit gate no longer passes")
                goal = self.resolve(run_id, run["goal_ref"])
                validate_completion(verification, goal)
                for check in verification.values():
                    require(check["status"] == "PASS" and check["rationale"] and verified(check["evidence_refs"], lambda r: self.resolve(run_id, r)), "unverified success criterion")
                    if goal["outcome_type"] in {"implementation", "artifact"}:
                        require(all(self.resolve(run_id, r)["observation_kind"] == "measured" for r in check["evidence_refs"]), "implementation completion needs directly observed validation")
                require(not important(package["uncertainties"]), "completion package retains unresolved important uncertainties")
                for gap in package["uncertainties"]:
                    require(type(gap) is dict and gap.get("rationale")
                            and type(gap.get("evidence_refs")) is list
                            and verified(gap["evidence_refs"], lambda r: self.resolve(run_id, r)),
                            "minor package uncertainty needs grounded impact/scope rationale")
                validate_artifacts(package["artifact_refs"])
                require(goal["outcome_type"] == "specification" or package["artifact_refs"], "implementation completion needs actual artifact locations")
                run["extensions"]["result_package_ref"] = package_ref
            if target in {"PARTIAL", "FAILED", "CANCELLED"} and package_ref:
                require(self.resolve(run_id, package_ref)["type"] == "SolutionPackage", "invalid result package")
                run["extensions"]["result_package_ref"] = package_ref
            run["state"] = target
            run["revision"] += 1
            self._save_run(run)
            self._event(run_id, "TRANSITION", {"state": target, "reason": reason, "evidence_refs": grounds,
                                               "verification": verification, "package_ref": package_ref})
            self._checkpoint(run)
        return run

    def reconcile(self, run_id, op_id, expected_revision, evidence_refs, resolution, reason):
        """Resolve an abandoned/stale/unknown intent after inspecting its real effects."""
        with self.transaction():
            run = self._run(run_id)
            self._expected(run, expected_revision)
            require(run["state"] not in TERMINAL, "cannot reconcile terminal run")
            require(resolution in {"not_executed", "result_recovered", "effects_inspected"}, "invalid reconciliation")
            require(reason and verified(evidence_refs, lambda r: self.resolve(run_id, r)), "reconciliation requires recorded observed evidence")
            row = self.db.execute("SELECT data FROM operations WHERE run_id=? AND id=?", (run_id, op_id)).fetchone()
            require(row is not None, "unknown pending operation")
            old = json.loads(row[0])
            require(not old["extensions"].get("resolved"), "operation already reconciled")
            require(not old["applied"] or old["result"].get("outcome") in {"UNKNOWN", "FAILED"}, "completed result must be reused")
            op = {**old, **self._meta(run_id, old["id"], "OperationRecord", previous=old, provenance=old["provenance"]),
                  "extensions": {**old["extensions"], "resolved": {"resolution": resolution,
                                 "evidence_refs": evidence_refs, "reason": reason}}}
            self._save_entity(run_id, op)
            self.db.execute("UPDATE operations SET data=? WHERE run_id=? AND id=?", (encode(op), run_id, op_id))
            run["revision"] += 1
            self._save_run(run)
            self._event(run_id, "RECONCILED", {"operation_id": op_id, "resolution": resolution, "evidence_refs": evidence_refs, "reason": reason})
            self._checkpoint(run)
        return op

    def status(self, run_id):
        run = self._run(run_id, compatible=False)
        documents = self.documents(run_id)
        checkpoint = self.db.execute("SELECT revision,digest FROM checkpoints WHERE run_id=? ORDER BY revision DESC LIMIT 1", (run_id,)).fetchone()
        operations = [json.loads(r[0]) for r in self.db.execute("SELECT data FROM operations WHERE run_id=? ORDER BY rowid", (run_id,))]
        latest_work = {}
        for operation in operations:
            latest_work[operation["extensions"]["work_signature"]] = operation
        applied = [o for o in operations if o["applied"] and not o["extensions"].get("resolved")]
        current = applied[-1:] + [o for o in latest_work.values()
                                 if o["result"].get("outcome") in {"FAILED", "UNKNOWN"}
                                 and not o["extensions"].get("resolved")]
        obligations = self._obligations(run_id)
        unresolved = feedback(documents) + self._propagation_feedback(obligations)
        for operation in current:
            for item in operation["result"].get("unresolved_items", []):
                if (type(item) is not dict or item.get("information_need") is not True) and item not in unresolved:
                    unresolved.append(item)
        return {"run": run, "compatible": run["schema_version"] == SCHEMA_VERSION and run["contract_version"] == CONTRACT_VERSION and run["contract_digest"] == contract_digest()
                and run.get("extensions", {}).get("implementation_digest") == implementation_digest(),
                "checkpoint_version": checkpoint[0] if checkpoint else None,
                "checkpoint_digest": checkpoint[1] if checkpoint else None,
                "stale_refs": [reference(d) for d in documents if d["validity_status"] == "STALE"],
                "candidates": [reference(d) for d in documents if d["type"] == "SolutionCandidate"],
                "candidate_validities": [{"candidate_ref": reference(d),
                    "functional_validity": "STALE" if d["validity_status"] != "VALID" else "VALID",
                    "selection_validity": d.get("extensions", {}).get("selection_validity", "UNASSESSED")}
                    for d in documents if d["type"] == "SolutionCandidate"],
                "pending_operations": [o for o in operations if (not o["applied"] or o["result"].get("outcome") == "UNKNOWN") and not o["extensions"].get("resolved")],
                "information_needs": question_records(documents),
                "learning_tasks": [d for d in documents if d["type"] == "LearningTask"],
                "tool_obligations": tool_obligations.projection(self.get(run_id, run['goal_ref']['id']), documents,
                    lambda p: self.resolve(run_id, p)),
                "goal_interpretation": goal_interpretation.projection(self.get(run_id, run["goal_ref"]["id"]), documents),
                "learning_frontier": frontier(documents, obligations),
                "propagation_obligations": obligations,
                "path_assessments": [p for o in operations for p in o["result"].get("path_assessments", [])],
                "unresolved_items": unresolved,
                "operation_feedback_history": [{"operation_ref": reference(o),
                    "unresolved_items": o["result"].get("unresolved_items", [])}
                    for o in operations if o["result"].get("unresolved_items")]}

    def observe(self, run_id):
        """Read actual persistent state for the host's next DDC, not choose actions."""
        state = self.status(run_id)
        state["goal"] = self.get(run_id, state["run"]["goal_ref"]["id"])
        state["capabilities"] = [d for d in self.documents(run_id) if d["type"] == "Capability"]
        operations = [json.loads(r[0]) for r in self.db.execute(
            "SELECT data FROM operations WHERE run_id=? ORDER BY rowid", (run_id,))]
        state["last_result"] = operations[-1]["result"] if operations else None
        state["state_digest"] = digest(state)
        return state

    def work_context(self, run_id, op_id=None, *, document_ids=None):
        with self.transaction(rollback=True):
            context = self._work_context(run_id,op_id)
            if document_ids is not None:
                require(type(document_ids) is list and document_ids
                        and all(type(identity) is str and identity for identity in document_ids)
                        and len(set(document_ids)) == len(document_ids),
                        'work-context document IDs must be explicit distinct nonempty strings')
                documents = {d['id']:d for d in self.documents(run_id)}
                require(all(identity in documents for identity in document_ids),
                        'work-context requested document does not exist')
                context['documents'] = [documents[identity] for identity in document_ids]
            return context

    def _work_context(self, run_id, op_id=None):
        """Project actual work boundaries; never select actions or approve a stop.

        Keep the exact observe revision/digest for host-authored DDC. Expose
        preserved-but-unapplied work even in PARTIAL; do not hide it as success.
        """
        state = self.observe(run_id)
        documents = self.documents(run_id)
        by_id = {d['id']:d for d in documents}
        operation = self.get(run_id,op_id) if op_id else None
        if operation:
            require(operation['type']=='OperationRecord','work-context requires an operation')
        selected = operation['intent'].get('learning_task_refs',[]) if operation else []
        plans = operation['intent'].get('learning_plan',[]) if operation else []
        consumers = [p for plan in plans for p in plan.get('judgment_target',{}).get('consumer_refs',[])]
        consumers += [edge['target_ref'] for edge in documents if edge['type']=='DependencyLink'
                      and any(p['id'] in {s['id'] for s in selected} for p in edge['sources'])]
        unique = {(p['id'],p['revision']):p for p in consumers}
        pending = [{'operation_ref':reference(o), 'action':o['action'],
                    'learning_task_refs':o['intent'].get('learning_task_refs',[]),
                    'actual_observations':o['extensions'].get('actual_observations',[]),
                    'outcome':o['result'].get('outcome'),
                    'expected_apply_revision':o['extensions']['expected_apply_revision']}
                   for o in state['pending_operations']]
        run = state['run']
        candidate_ref = run['extensions'].get('committed_candidate_ref')
        review_ref = run['extensions'].get('committed_review_ref')
        package_ref = run['extensions'].get('result_package_ref')
        package = by_id.get(package_ref['id']) if package_ref else None
        adoption_errors = []
        if candidate_ref is None or review_ref is None:
            adoption_errors.append('no stored committed candidate/review')
        else:
            adoption_errors += self._commit_gate(run_id, candidate_ref, review_ref,
                documents, lambda pointer: self.resolve(run_id, pointer))['errors']
        if not package or package['type'] != 'SolutionPackage':
            adoption_errors.append('no stored result package')
        else:
            if package_ref != reference(package):
                adoption_errors.append('stored result package reference is stale')
            if package['candidate_ref'] != candidate_ref or package['review_ref'] != review_ref:
                adoption_errors.append('result package differs from stored adoption')
            if run['state'] == 'COMPLETED':
                try:
                    validate_artifacts(package['artifact_refs'])
                except ValueError as exc:
                    adoption_errors.append(str(exc))
        return {'run_ref':reference(state['run']), 'state':state['run']['state'],
            'compatible':state['compatible'],
            'identity':{'contract_version':state['run']['contract_version'],
                'contract_digest':state['run']['contract_digest'],
                'implementation_digest':state['run']['extensions'].get('implementation_digest')},
            'revision':state['run']['revision'], 'state_digest':state['state_digest'],
            'pending_propagation_count':sum(o['status'] == 'PENDING' for o in state['propagation_obligations']),
            'goal':state['goal'],
            'requirements_context':requirements_context(state['goal'], documents),
            'return_boundary':{'committed_candidate_ref':candidate_ref, 'committed_review_ref':review_ref,
                'result_package_ref':package_ref, 'adoption_errors':adoption_errors,
                'scope':'Current stored adoption structure only. Not semantic approval, '
                        'permission to stop, or interception of natural-language replies.'},
            'operation':({'operation_ref':reference(operation), 'action':operation['action'],
                'intent':operation['intent'], 'applied':operation['applied'],
                'consumption_link_errors': consumption_link_errors(plans, documents),
                'actual_observations':operation['extensions'].get('actual_observations',[]),
                'result_refs':operation['result'].get('result_refs',[]),
                'outcome':operation['result'].get('outcome'),
                'expected_apply_revision':operation['extensions']['expected_apply_revision']} if operation else None),
            'selected_tasks':[{'requested_ref':p,'current':by_id.get(p['id']),
                'reference_current':p==reference(by_id[p['id']]) if p['id'] in by_id else False} for p in selected],
            'consumers':[{'declared_ref':p,'current':by_id.get(p['id']),
                'reference_current':p==reference(by_id[p['id']]) if p['id'] in by_id else False} for p in unique.values()],
            'assets':[{'asset_ref':reference(d), **{k:d[k] for k in
                ('identity','kind','provided_capability_refs','applicability','availability','understanding')}}
                for d in documents if d['type']=='KnowledgeAsset'],
            'candidates':[{'candidate_ref':reference(d),'disposition':d['disposition'],
                'asset_refs':d['asset_refs'],'gaps':d['gaps'],'comparison_rationale':d['comparison_rationale'],
                'validity_status':d['validity_status']} for d in documents if d['type']=='SolutionCandidate'],
            'unfinished_learning':[{'task_ref':reference(d),'question':d['question'],
                'assessment':d['assessment'],'answer_status':d['answer']['status'],
                'understanding_status':d['understanding']['status'],
                'disposition':d['disposition'],'work_state':d['work_state'],
                'closure_assessment':d['closure_assessment']}
                for d in state['learning_tasks'] if d['disposition'] not in {'CLOSED','MERGED'}],
            'pending_operations':pending,
            'unapplied_observation_count':sum(len(o['actual_observations']) for o in pending),
            'learning_frontier':state['learning_frontier'],
            'propagation_obligations':state['propagation_obligations'],
            'unresolved_items':state['unresolved_items'], 'stale_refs':state['stale_refs'],
            'adoption':{'committed_candidate_ref':state['run']['extensions'].get('committed_candidate_ref'),
                        'result_package_ref':state['run']['extensions'].get('result_package_ref')},
            'scope':'Observed records only. Host must evaluate knowledge, candidate use, continuation/stop and goal fit. No automatic PASS, relevance or PARTIAL authorization.'}

    def _project_changes(self, run_id, changes):
        """Shared deterministic prepare projection. No writes, assessment or ref repair."""
        documents = {d["id"]: d for d in self.documents(run_id)}
        for change in changes:
            previous = documents.get(change["id"])
            documents[change["id"]] = {**change, **self._meta(run_id, change["id"], change["type"],
                previous=previous, provenance=change.get("provenance", []),
                validity=change.get("validity_status", "VALID"))}
        goal = next(d for d in documents.values() if d['type'] == 'GoalSpec' and
                    d['id'] == self._run(run_id)['goal_ref']['id'])
        for question in tool_obligations.registration_changes(goal, documents.values(), lambda p: documents[p['id']]):
            documents[question['id']] = {**question, **self._meta(run_id, question['id'], 'LearningTask')}
        previous = {d["id"]: self.get(run_id, d["id"]) for d in documents.values()
                    if any(c["id"] == d["id"] for c in changes)
                    and self.db.execute("SELECT 1 FROM entities WHERE run_id=? AND id=?", (run_id, d["id"])).fetchone()}
        invalidated = self._invalidation_targets(list(documents.values()), set(previous),
            {c["id"] for c in changes})
        for identity in invalidated:
            documents[identity] = self._invalidated_document(run_id, documents[identity], set(previous), invalidated)
        new_obligations = self._derive_obligations(run_id, previous, documents, invalidated)
        return documents, previous, invalidated, new_obligations

    def prepare(self, run_id, op_id, result):
        """Serialize host-authored results and forward questions without resolving them.

        This does not select actions, label evidence or fill Review/K judgments.
        Apply checks the actual post-invalidation state atomically afterwards.
        """
        self._run(run_id)
        require(result.get("operation_id") == op_id, "wrong operation output id")
        operation = self.get(run_id, op_id)
        require(operation["type"] == "OperationRecord", "prepare requires an operation")

        def host_content(payload):
            return {**payload, **{field: [v for v in payload.get(field, [])
                    if type(v) is not dict or v.get("information_need") is not True]
                    for field in ("unresolved_items", "next_decision_inputs")}}

        if operation["applied"]:
            require(host_content(result) == host_content(operation["result"]),
                    "operation already applied with different host result")
            return operation["result"]
        documents, previous, invalidated, new_obligations = self._project_changes(
            run_id, result.get("proposed_state_changes", []))
        pending = self._obligations(run_id, new_obligations, result.get("propagation_resolutions", []))
        needs = feedback(documents.values()) + self._propagation_feedback(pending)
        result = dict(result)
        for field in ("unresolved_items", "next_decision_inputs"):
            result[field] = host_content(result)[field] + needs
        return result

    def restore(self, run_id):
        self._run(run_id)
        row = self.db.execute("SELECT data,digest FROM checkpoints WHERE run_id=? ORDER BY revision DESC LIMIT 1", (run_id,)).fetchone()
        require(row is not None, "no saved checkpoint")
        snapshot = json.loads(row[0])
        require(digest(snapshot) == row[1], "checkpoint integrity failure")
        require(snapshot["run"] == self._run(run_id), "checkpoint differs from stored run")
        current = [d for d in self.documents(run_id) if d["type"] != "Checkpoint"]
        saved = [d for d in snapshot["documents"] if d["type"] != "Checkpoint"]
        require(current == saved, "stored objects differ from checkpoint")
        operations = [json.loads(r[0]) for r in self.db.execute("SELECT data FROM operations WHERE run_id=? ORDER BY id", (run_id,))]
        require(operations == sorted(snapshot["operations"], key=lambda o: o["id"]), "stored operations differ from checkpoint")
        return {"snapshot": snapshot, "status": self.status(run_id),
                "recovery": "inspect pending external effects, reuse saved results, reconcile before retry; no automatic state change"}

    def migrate(self, run_id):
        """Conservative linked import; never rewrite an old run's identity/results.

        Imports raw question/answer history as UNASSESSED/PROVISIONAL work, not as
        new semantic approval. Existing observations and artifacts stay in origin.
        """
        old_run = self._run(run_id, compatible=False)
        require(old_run["schema_version"] == 1 and old_run["contract_version"] == "3.1",
                "migration supports schema-1/v3.1 only; use a matching archive otherwise")
        old_goal = self.get(run_id, old_run["goal_ref"]["id"], old_run["goal_ref"]["revision"])
        goal = {k: old_goal[k] for k in FIELDS["GoalSpec"]}
        goal["id"] = old_goal["id"]
        goal["extensions"] = {"goal_alignment": old_goal.get("extensions", {}).get("goal_alignment") or {
            "facets": [{"id": "legacy-source", "source_quote": old_goal["source_request"],
                "interpretation": "Imported original request; preservation needs host reassessment",
                "criterion_ids": [c["id"] for c in old_goal["success_criteria"]]}],
            "preservation_rationale": "History import only; original goal adequacy is not approved"}}
        original_docs = self.documents(run_id)
        original_hash = digest({"run": old_run, "documents": original_docs})
        new_run = self.create(goal, old_run["environment"], old_run["resource_observations"], parent_run_id=run_id)
        records = [("goal-preservation", "Does the imported goal preserve the original purpose and context?", None)]
        for owner in original_docs:
            for context, q in questions(owner):
                if type(q) is dict and "question" in q:
                    records.append((owner["id"] + "/" + context + "/" + q.get("id", "legacy"), q["question"], q))
                elif type(q) is str and q.strip():
                    records.append((owner["id"] + "/" + context + "/" + digest(q)[:16], q, None))
        for op in self.status(run_id)["pending_operations"]:
            records.append(("pending-effect/" + op["id"],
                "What actually happened in the pending original operation " + op["id"] + " before any retry?", None))
        mapping = []
        with self.transaction():
            for index, (key, question, legacy) in enumerate(records):
                identity = "imported-" + digest([run_id, key])[:20]
                answer = (legacy or {}).get("answer", "")
                task = {**self._meta(new_run["id"], identity, "LearningTask"),
                    "goal_ref": new_run["goal_ref"], "question": question,
                    "subject": {"concept": "Imported question requiring contextual reassessment"},
                    "context": {"purpose": (legacy or {}).get("decision_impact", "Preserve original goal"),
                        "environment": old_run["environment"], "version": "v3.1 history → v3.2 reassessment",
                        "conditions": [], "constraints": old_goal["explicit_constraints"], "scope": "Imported scope is provisional"},
                    "origin_refs": [new_run["goal_ref"]], "goal_connections": [{"goal_ref": new_run["goal_ref"],
                        "facet_ids": [f["id"] for f in goal["extensions"]["goal_alignment"]["facets"]],
                        "path_refs": [], "rationale": "Preserve imported source connection; reassess semantic adequacy"}],
                    "answer_requirements": [{"id": "reassess", "ability": "Judge current contextual validity",
                        "discriminator": "Read the original records and verify applicable evidence",
                        "sufficient_when": "Host grounds current ability and scope", "evidence_requirement": "Current claim-specific observations"}],
                    "assessment": {"relevance": "UNASSESSED", "materiality": "UNKNOWN", "role": "SCOPING",
                        "rationale": "Old approval is not current semantic evidence", "evidence_refs": [], "unknowns": ["Current applicability"]},
                    "answer": {"status": "PROVISIONAL" if answer else "UNANSWERED", "claims": [{"id": "historic-answer",
                        "text": answer, "evidence_refs": [], "source_locator": run_id + ":" + key,
                        "conditions": ["Unverified historical answer"], "inference": False}] if answer else [],
                        "counterevidence_refs": [], "gaps": [], "scope": "Historical answer only"},
                    "understanding": {"status": "UNASSESSED", "abilities": [], "k_level": None},
                    "expansion": {"status": "UNASSESSED", "discoveries": [], "scope_rationale": "Not yet reassessed", "evidence_refs": []},
                    "dependency_refs": [], "work_state": "READY", "disposition": "OPEN", "closure_assessment": {},
                    "reopen_conditions": [], "extensions": {"legacy_origin": run_id + ":" + key,
                        "legacy_status": (legacy or {}).get("status"), "next_action": "DISCOVER_KNOWLEDGE"}}
                self._save_entity(new_run["id"], task)
                mapping.append({"origin": run_id + ":" + key, "task_ref": reference(task)})
            new_run["extensions"]["migration"] = {"origin_run": run_id, "origin_snapshot_digest": original_hash,
                "imported_questions": mapping, "not_imported_as_valid": ["proof", "Review", "Commit", "completion", "K sufficiency"],
                "pending_origin_operations": [o["id"] for o in self.status(run_id)["pending_operations"]]}
            new_run["revision"] += 1
            self._save_run(new_run)
            self._event(new_run["id"], "LINKED_MIGRATION", new_run["extensions"]["migration"])
            self._checkpoint(new_run)
        require(original_hash == digest({"run": self._run(run_id, compatible=False), "documents": self.documents(run_id)}),
                "migration changed original history")
        return {"run": new_run, "mapping": mapping, "origin_preserved": True,
                "scope": "Conservative linked import; host must reassess original goal, evidence and pending external effects"}

    def resume(self, run_id, expected_revision, reason, evidence_refs):
        restored = self.restore(run_id)
        require(not restored["status"]["pending_operations"], "inspect/reconcile pending operations before resume")
        run = restored["status"]["run"]
        if run["state"] == "ACTIVE":
            self._expected(run, expected_revision)
            require(reason and verified(evidence_refs, lambda r: self.resolve(run_id, r)), "ACTIVE recovery needs host-liveness/effects inspection evidence")
            return run
        require(run["state"] in {"SUSPENDED", "BLOCKED"}, "run cannot be resumed")
        require(reason and verified(evidence_refs, lambda r: self.resolve(run_id, r)), "resume needs resolved-cause evidence")
        return self.transition(run_id, "ACTIVE", expected_revision, reason, evidence_refs)

    def result(self, run_id):
        status = self.status(run_id)
        packages = [d for d in self.documents(run_id) if d["type"] == "SolutionPackage"]
        return {"run_id": run_id, "state": status["run"]["state"], "contract_version": status["run"]["contract_version"],
                "packages": packages, "status": status}

    def explain(self, run_id):
        self._run(run_id, compatible=False)
        return {"decisions": [d for d in self.documents(run_id) if d["type"] == "DecisionRecord"],
                "events": [dict(r) | {"data": json.loads(r["data"])} for r in self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,))]}
