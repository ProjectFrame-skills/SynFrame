"""Grounded AND/OR graph evaluation, explicit I/O and comparable attributes."""

from collections import defaultdict
from .schema import ContractError, require, finite_json


def reference(doc):
    return {"id": doc["id"], "revision": doc["revision"]}


def verified(refs, resolve):
    if not refs:
        return False
    try:
        evidence = [resolve(r) for r in refs]
        return all(e["type"] == "EvidenceRecord" and e["validity_status"] == "VALID"
                   and e["verification_status"] == "VERIFIED" for e in evidence)
    except ContractError:
        return False


def evaluate(candidate, documents, resolve):
    """Grounded least fixed point with an explicit selected functional proof.

    Group keys include target and relation. OR catalogs may retain an old unused
    source revision; only a currently grounded witness enters this proof.
    """
    docs = {d["id"]: d for d in documents}
    assets = {r["id"]: resolve(r) for r in candidate["asset_refs"]}
    caps = {d["id"]: d for d in documents if d["type"] == "Capability"
            and d["goal_ref"] == candidate["goal_ref"]}
    groups = defaultdict(list)
    conflicts = []
    for link in documents:
        if link["type"] != "DependencyLink" or link["validity_status"] != "VALID":
            continue
        relation = link["relation"]
        if relation == "CONFLICTS":
            conflicts.append(link)
        elif relation in {"AND", "OR", "REQUIRES", "PROVIDES", "TRANSFORMS"}:
            groups[(link["target_ref"]["id"], relation, link["group_id"])].append(link)

    def current(pointer):
        try:
            resolve(pointer)
            return True
        except ContractError:
            return False

    def witness(group, proofs):
        sources = [r for l in group for r in l["sources"]]
        if group[0]["relation"] == "OR":
            usable = [r for l in group if verified(l["evidence_refs"], resolve) and current(l["target_ref"])
                      for r in l["sources"] if r["id"] in proofs and current(r)]
            # Explicit host witness wins. Remaining witnesses are equivalent for
            # this boolean proof only; this is not candidate quality ranking.
            key = "/".join((group[0]["target_ref"]["id"], "OR", group[0]["group_id"]))
            choice = candidate.get("extensions", {}).get("proof_choices", {}).get(key)
            if choice:
                usable = [r for r in usable if r["id"] == choice]
            return usable[:1] or None
        if not all(verified(l["evidence_refs"], resolve) and current(l["target_ref"]) for l in group):
            return None
        usable = [r for r in sources if r["id"] in proofs and current(r)]
        return sources if len(usable) == len(sources) else None

    def prerequisites(identity, proofs):
        required = [g for (target, relation, _),g in groups.items()
                    if target == identity and relation == "REQUIRES"]
        witnesses = [witness(g, proofs) for g in required]
        if any(w is None for w in witnesses):
            return None
        return [(g,w) for g,w in zip(required,witnesses)]

    conditions = candidate.get("extensions", {}).get("condition_refs", [])
    proofs = {p["id"]: [] for p in conditions if verified([p], resolve)}
    while True:
        additions = {}
        for identity, asset in assets.items():
            grounds = [r for r in asset["provenance"] if isinstance(r, dict) and set(r) == {"id", "revision"}]
            pre = prerequisites(identity, proofs)
            if (identity not in proofs and asset["validity_status"] == "VALID" and
                asset["availability"] in {"available", "knowledge_only"} and verified(grounds, resolve) and pre is not None):
                additions[identity] = pre
        for identity, capability in caps.items():
            if identity in proofs or capability["validity_status"] != "VALID":
                continue
            pre = prerequisites(identity, proofs)
            if pre is None:
                continue
            for (target, relation, _), group in groups.items():
                if target == identity and relation != "REQUIRES":
                    w = witness(group, proofs)
                    if w is not None:
                        additions[identity] = pre + [(group, w)]
                        break
        if not additions:
            break
        proofs.update(additions)
    mandatory = {c["id"] for c in caps.values() if c["mandatory"]}
    require(mandatory, "no mandatory capability has been derived for the goal")
    roots = mandatory | set(assets) | {r["id"] for r in candidate["capability_refs"]} | {p["id"] for p in conditions}
    used, projected = set(), {}
    queue = list(roots)
    while queue:
        identity = queue.pop()
        if identity in used:
            continue
        used.add(identity)
        for group, sources in proofs.get(identity, []):
            for link in group:
                selected_sources = [r for r in link["sources"] if r in sources]
                # OR group links without the witness are catalog entries only.
                if link["relation"] == "OR" and not selected_sources:
                    continue
                projected[link["id"]] = selected_sources
            queue.extend(r["id"] for r in sources)
    active_conflicts = []
    for link in conflicts:
        endpoints = [link["target_ref"], *link["sources"]]
        if all(r["id"] in used for r in endpoints):
            # A known structural conflict with unknown applicability is unresolved,
            # never silently equivalent to compatibility.
            active_conflicts.append(link["id"])
            projected[link["id"]] = link["sources"]
    return {"satisfied": sorted(proofs), "mandatory": sorted(mandatory),
            "missing": sorted((mandatory | {r["id"] for r in candidate["capability_refs"]}) - set(proofs)),
            "conflicts": sorted(active_conflicts), "ungrounded_assets": sorted(set(assets) - set(proofs)),
            "proof_nodes": sorted(used), "proof_links": projected}


def check_io(candidate, resolve):
    assets = {r["id"]: resolve(r) for r in candidate["asset_refs"]}
    connected = set()
    errors = []
    for connection in candidate["connections"]:
        a = assets.get(connection["from_ref"]["id"])
        b = assets.get(connection["to_ref"]["id"])
        if a is None or b is None:
            errors.append("connection endpoint is not a selected asset")
            continue
        outputs = {p["name"]: p["type"] for p in a["outputs"]}
        inputs = {p["name"]: p["type"] for p in b["inputs"]}
        out, inp = connection["output"], connection["input"]
        if out not in outputs or inp not in inputs:
            errors.append("unknown I/O port")
        elif outputs[out] != inputs[inp]:
            errors.append(f"incompatible I/O types {outputs[out]} → {inputs[inp]}")
        elif not verified(connection["evidence_refs"], resolve):
            errors.append("I/O binding lacks valid verified evidence")
        else:
            connected.add((b["id"], inp))
    for asset in assets.values():
        for port in asset["inputs"]:
            if (asset["id"], port["name"]) not in connected:
                errors.append(f"unbound input {asset['id']}.{port['name']}")
    return errors


def predicate(candidate, expression):
    value = candidate
    missing = False
    for key in expression["path"].split("."):
        if not isinstance(value, dict) or key not in value:
            missing = True
            break
        value = value[key]
    op, expected = expression["op"], expression["value"]
    if op == "exists":
        return (not missing) == expected
    if missing or value is None:
        return None
    try:
        return {"eq": lambda: type(value) is type(expected) and value == expected,
                "in": lambda: value in expected,
                "not_in": lambda: value not in expected,
                "gte": lambda: type(value) in (int, float) and type(expected) in (int, float) and value >= expected,
                "lte": lambda: type(value) in (int, float) and type(expected) in (int, float) and value <= expected}[op]()
    except (KeyError, TypeError):
        return None


def pareto(left, right, dimensions):
    """No fabricated scalar scores; unknown on any dimension prevents dominance."""
    require(type(left) is dict and type(right) is dict and type(dimensions) is dict, "comparison expects attribute objects")
    finite_json(left); finite_json(right)
    require(dimensions and all(v in {"min", "max"} for v in dimensions.values()), "invalid comparison dimensions")
    better, worse, unknown = [], [], []
    for key, direction in dimensions.items():
        a, b = left.get(key), right.get(key)
        if type(a) not in (int, float) or type(b) not in (int, float):
            unknown.append(key)
        elif a != b:
            (better if ((a < b) == (direction == "min")) else worse).append(key)
    return {"left_dominates": bool(better) and not worse and not unknown,
            "right_dominates": bool(worse) and not better and not unknown,
            "better": better, "worse": worse, "unknown": unknown}
