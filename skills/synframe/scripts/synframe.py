#!/usr/bin/env python3
"""SynFrame skill helper. The host performs reasoning and external work."""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from synframe_core import Core, ContractError
from synframe_core.schema import schema_catalog
from synframe_core.graph import pareto
from synframe_core.files import file_sha256


def read_json(path):
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ContractError("invalid JSON number " + value)))


def pointer(text):
    try:
        identity, revision = text.rsplit("@", 1)
        return {"id": identity, "revision": int(revision)}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use entity-id@revision") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=str(Path.cwd() / ".synframe"), help="allowed state directory outside the skill")
    parser.add_argument('--compact', action='store_true', help='machine JSON without formatting whitespace; all values retained')
    commands = parser.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("schema", help="show entity fields, enums and nested shapes")
    schema.add_argument('--entity', help='show only the requested entity serialization contract')
    schema.add_argument('--entities', nargs='+', help='explicit independent entity contracts in one response')
    schema.add_argument('--for-command', '--command', dest='schema_command', help='show command input contract (transition)')
    contract = commands.add_parser('read-contract', help='manifest or bounded exact bundled contract text; no reading/sufficiency judgment')
    contract.add_argument('--name')
    contract.add_argument('--offset', type=int, default=0)
    contract.add_argument('--limit', type=int, default=6000)
    contract.add_argument('--expected-sha')
    contract.add_argument('--retained', help='JSON file of host-declared ranges actually retained in current context')
    learning_basis = commands.add_parser("learning-basis", help="hash current task closure basis; no adequacy judgment")
    learning_basis.add_argument("--input", required=True)
    compare = commands.add_parser("compare", help="compare only known numeric Pareto dimensions")
    compare.add_argument("--input", required=True)
    artifact = commands.add_parser("artifact", help="record actual artifact path/hash/source")
    artifact.add_argument("path")
    artifact.add_argument("--source", required=True)
    solve = commands.add_parser("solve", help="register compiled GoalSpec; host then reasons")
    solve.add_argument("--input", required=True)
    solve.add_argument("--environment")
    solve.add_argument("--resources")
    solve.add_argument("--parent-run")
    for name in ["status", "observe", "observe-result", "prepare", "finish", "preflight", "patch-refs", "review-context", "work-context", "resume", "migrate", "result", "explain", "cancel", "intent", "apply", "transition", "reconcile", "snapshot", "gate", "get", "list"]:
        sub = commands.add_parser(name)
        sub.add_argument("--run", required=True)
        if name in {"intent", "apply", "prepare", "finish", "preflight", "patch-refs", "transition", "reconcile", "observe-result"}:
            sub.add_argument("--input", required=True, help="JSON file or - for stdin")
        if name in {"resume", "cancel"}:
            sub.add_argument("--input", help="resume reason/evidence; omit to inspect saved state")
        if name in {"resume", "cancel", "transition", "reconcile", "observe-result"}:
            sub.add_argument("--expected", type=int)
        if name in {"apply", "prepare", "finish", "preflight", "reconcile", "observe-result"}:
            sub.add_argument("--operation", required=True)
        if name == 'work-context':
            sub.add_argument('--operation')
        if name in {"snapshot", "gate", "review-context"}:
            sub.add_argument("--candidate", type=pointer, required=True)
        if name == "gate":
            sub.add_argument("--review", type=pointer, required=True)
        if name == "get":
            sub.add_argument("--id", required=True)
            sub.add_argument("--revision", type=int)
    args = parser.parse_args(argv)
    core = None
    try:
        if args.command == "schema":
            if args.entities is not None:
                if args.entity or args.schema_command or len(set(args.entities)) != len(args.entities):
                    raise ContractError('select distinct entities OR entity OR command')
                output = {'entities':{name:schema_catalog(name) for name in args.entities},
                    'scope':'Complete requested schemas only; no judgment defaults or fixed query pipeline'}
            else:
                output = schema_catalog(args.entity, command=args.schema_command)
        elif args.command == 'read-contract':
            from synframe_host import read_contract
            output = read_contract(Path(__file__).resolve().parents[1],args.name,args.offset,args.limit,args.expected_sha,
                retained=read_json(args.retained) if args.retained else None)
        elif args.command == "learning-basis":
            from synframe_core.learning import basis
            output = {"basis": basis(read_json(args.input)), "semantic_scope": "content hash only; host assesses sufficiency"}
        elif args.command == "compare":
            payload = read_json(args.input)
            output = pareto(payload["left"], payload["right"], payload["dimensions"])
        elif args.command == "artifact":
            p = Path(args.path).expanduser().resolve()
            output = {"path": str(p), "sha256": file_sha256(p), "source": args.source}
        else:
            core = Core(args.state)
            payload = read_json(args.input) if hasattr(args, "input") and args.input else None
            command = args.command
            if command == "solve":
                output = core.create(payload, read_json(args.environment) if args.environment else None,
                                     read_json(args.resources) if args.resources else None, args.parent_run)
            elif command == "status":
                output = core.status(args.run)
            elif command == "observe":
                output = core.observe(args.run)
            elif command == "observe-result":
                output = core.record_observation(args.run, args.operation, args.expected, payload)
            elif command == "migrate":
                output = core.migrate(args.run)
            elif command == "prepare":
                output = core.prepare(args.run, args.operation, payload)
            elif command == "finish":
                output = core.apply(args.run, args.operation, core.prepare(args.run, args.operation, payload))
            elif command == 'preflight':
                output = core.preflight(args.run, args.operation, payload)
            elif command == 'patch-refs':
                output = core.patch_refs(args.run, payload)
            elif command == 'review-context':
                output = core.review_context(args.run, args.candidate)
            elif command == 'work-context':
                output = core.work_context(args.run, args.operation)
            elif command == "resume":
                output = core.resume(args.run, args.expected, **payload) if payload else core.restore(args.run)
            elif command == "result":
                output = core.result(args.run)
            elif command == "explain":
                output = core.explain(args.run)
            elif command == "cancel":
                if payload is None:
                    raise ContractError("cancel needs --input with user cancellation reason")
                output = core.transition(args.run, "CANCELLED", args.expected, **payload)
            elif command == "intent":
                output = core.begin(args.run, payload)
            elif command == "apply":
                output = core.apply(args.run, args.operation, payload)
            elif command == "transition":
                output = core.transition(args.run, expected_revision=args.expected, **payload)
            elif command == "reconcile":
                output = core.reconcile(args.run, args.operation, args.expected, **payload)
            elif command == "snapshot":
                output = core.snapshot(args.run, args.candidate)
            elif command == "gate":
                output = core.commit_gate(args.run, args.candidate, args.review)
            elif command == "get":
                output = core.get(args.run, args.id, args.revision)
            elif command == "list":
                output = core.documents(args.run)
        formatting = {'separators':(',',':')} if args.compact else {'indent':2}
        print(json.dumps(output, ensure_ascii=False, allow_nan=False, **formatting))
        return 2 if isinstance(output, dict) and output.get("passed") is False else 0
    except (ContractError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc), "applied": False,
            **getattr(exc,'details',{})}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if core:
            core.close()


if __name__ == "__main__":
    sys.exit(main())
