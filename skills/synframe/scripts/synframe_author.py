"""Reusable explicit host input runner; no inference, defaults or pipeline.

Each invocation saves its exact input and separate output/error before returning.
Only the host supplies DDC, answers, K, unresolved work, Review and closure. The
runner uses the installed adjacent HostIO and existing core validation paths.
"""
import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

from synframe_host import HostIO, HostError
from synframe_core.schema import ref, schema_catalog


RESULT_ARGUMENTS = {
    'result_ids', 'preserved_refs', 'evidence_refs', 'unresolved_items',
    'observed_effects', 'next_decision_inputs', 'outcome', 'learning_results',
    'propagation_resolutions', 'path_assessments',
}
FIELDS = {
    'begin': {'action', 'judgment', 'intent', 'input_refs', 'evidence_refs', 'key'},
    'preserve-files': {'operation_ref', 'files'},
    'build-result': {'operation_ref', 'observed_state', 'changes'} | RESULT_ARGUMENTS,
    'result': {'operation_ref', 'observed_state', 'changes'} | RESULT_ARGUMENTS,
    'finish': {'operation_ref', 'observed_state', 'result'},
    'complete': {'observed_state', 'package_ref', 'reason', 'evidence_refs', 'verification'},
    'context': {'operation_ref', 'document_ids'},
}


def input_contract(command, entity_types=None):
    if command not in FIELDS:
        raise ValueError('unknown authoring command')
    contract = {'command': command, 'required_fields': sorted(FIELDS[command]),
        'state_binding': 'Use the exact observed revision/state_digest; never fetch a new digest to stamp old judgments.',
        'changes': {'complete_record': 'Existing canonical entity patch',
            'field_edits': {'base_ref': '{id, revision}, must still be current',
                'replacements': [{'path': ['dictionary', 'keys'], 'value': 'explicit value'}],
                'removals': [['dictionary', 'key']]},
            'scope': 'No list-index edits, implicit merge, metadata edits or automatic closure hash.'},
        'scope': 'Serialization contract only. All semantic values and empty lists must be explicitly authored. '
            'Record direct observations separately from interpretations of their meaning. A measured host comparison '
            'proves that comparison occurred, not that its conclusion is true. File identity is not claim verification. '
            'Each learning_results.discovery_ids lists all retained and new discoveries in that resulting task expansion, '
            'not just discoveries added during this operation; assess their current dispositions without automatic filling.'}
    if entity_types is not None:
        if not entity_types or len(set(entity_types)) != len(entity_types):
            raise ValueError('schema bundle needs explicit distinct entity types')
        contract['entities'] = {name:schema_catalog(name) for name in entity_types}
    if command == 'finish':
        contract['required_fields'].remove('result')
        contract['exactly_one'] = {'result':'Complete explicitly assessed canonical result',
            'result_file':{'path':'Exact saved canonical result JSON file', 'sha256':'Its actual full-file SHA256'}}
    if command == 'context':
        contract['output_contract'] = schema_catalog(command='work-context')
    return contract


def _exact(payload, fields, name):
    if type(payload) is not dict or set(payload) != fields:
        supplied = set(payload) if type(payload) is dict else set()
        raise ValueError(f'{name} fields: missing={sorted(fields-supplied)}, unexpected={sorted(supplied-fields)}')


def _operation(io, pointer):
    ref(pointer)
    operation = io.call('get', id=pointer['id'], revision=pointer['revision'])
    if operation['type'] != 'OperationRecord':
        raise ValueError('operation_ref must identify an exact saved OperationRecord')
    return operation


def _observed(io, declared, operation):
    _exact(declared, {'revision', 'state_digest'}, 'observed_state')
    if type(declared['revision']) is not int or type(declared['state_digest']) is not str:
        raise ValueError('observed state needs an integer revision and exact digest string')
    current = io.work_context(operation)
    if any(declared[key] != current[key] for key in declared):
        raise ValueError('observed state changed; inspect current work and reassess without automatic rebasing')
    return current


def _result_file(pointer):
    _exact(pointer, {'path','sha256'}, 'result_file')
    if type(pointer['path']) is not str or not pointer['path'] or type(pointer['sha256']) is not str:
        raise ValueError('result_file needs an explicit path and SHA256')
    raw = Path(pointer['path']).expanduser().resolve().read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer['sha256']:
        raise ValueError('result file changed; inspect its actual contents and reassess')
    return raw, _parse(raw)


def _changes(io, changes):
    if type(changes) is not list:
        raise ValueError('changes must be an explicit list')
    # Read all requested bases once, at the same observed snapshot.
    deltas = [item for item in changes if type(item) is dict and 'base_ref' in item]
    if deltas:
        for item in deltas:
            _exact(item, {'base_ref', 'replacements', 'removals'}, 'field edits')
            ref(item['base_ref'])
        ids = list(dict.fromkeys(item['base_ref']['id'] for item in deltas))
        bases = {doc['id']:doc for doc in io.work_context(document_ids=ids)['documents']}
    output = []
    for item in changes:
        if type(item) is dict and 'base_ref' in item:
            output.append(HostIO.edit_fields(bases[item['base_ref']['id']], **{
                'expected_ref':item['base_ref'], 'replacements':item['replacements'], 'removals':item['removals']}))
        else:
            output.append(item)
    return output


def execute(io, command, payload):
    """Execute one explicitly selected I/O operation. No auto retry or stop."""
    fields = FIELDS[command]
    if command == 'finish' and type(payload) is dict and 'result_file' in payload:
        fields = fields - {'result'} | {'result_file'}
    _exact(payload, fields, command)
    if command == 'begin':
        if type(payload['key']) is not str or not payload['key'].strip():
            raise ValueError('begin needs an explicit nonempty idempotency key')
        if type(payload['input_refs']) is not list or type(payload['evidence_refs']) is not list:
            raise ValueError('begin needs explicit input_refs/evidence_refs lists')
        return io.begin(payload['action'], payload['judgment'], payload['intent'],
            input_refs=payload['input_refs'], evidence_refs=payload['evidence_refs'], key=payload['key'])
    if command == 'complete':
        context = _observed(io, payload['observed_state'], None)
        return io.complete(context, package_ref=payload['package_ref'],
            reason=payload['reason'], evidence_refs=payload['evidence_refs'], verification=payload['verification'])
    if command == 'context':
        operation = _operation(io, payload['operation_ref']) if payload['operation_ref'] is not None else None
        return io.work_context(operation, document_ids=payload['document_ids'])
    operation = _operation(io, payload['operation_ref'])
    if command == 'preserve-files':
        return io.preserve_files(operation, payload['files'])
    if command == 'finish':
        result = _result_file(payload['result_file'])[1] if 'result_file' in payload else payload['result']
        # Existing exact-result replay is a no-op, not a fresh judgment. Delegate
        # its equality check to the same core finish path without stamping a new
        # observation onto the retained input. Different results still reject.
        current = io.call('get', id=operation['id'])
        if not current['applied']:
            _observed(io, payload['observed_state'], operation)
        return io.finish(operation, result)
    _observed(io, payload['observed_state'], operation)
    changes = _changes(io, payload['changes'])
    result = io.build_result(operation, changes,
        expected_revision=payload['observed_state']['revision'],
        **{key:payload[key] for key in RESULT_ARGUMENTS})
    if command == 'build-result':
        return result
    return io.finish(operation, result)


def _json_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _parse(raw):
    def nonfinite(value):
        raise ValueError('nonfinite JSON value: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_json_pairs, parse_constant=nonfinite)


def _write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        stream.write('\n')


def _locations(state, records):
    """Reject skill-local writes before creating even the invocation journal."""
    state = Path(state).expanduser().resolve()
    records = Path(records).expanduser().resolve() if records else state/'authoring'
    roots = {Path(__file__).resolve().parents[1],
        (Path.home()/'.codex/skills/synframe').resolve(),
        (Path.home()/'.agents/skills/synframe').resolve()}
    if os.environ.get('CODEX_HOME'):
        roots.add((Path(os.environ['CODEX_HOME']).expanduser()/'skills/synframe').resolve())
    if any(path == skill or skill in path.parents for path in (state, records) for skill in roots):
        raise ValueError('state and authoring records must be outside the installed skill')
    return state, records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default='.synframe')
    parser.add_argument('--run')
    parser.add_argument('--records', help='Append-only invocation records; default <state>/authoring')
    parser.add_argument('--receipt-only', action='store_true', help='Print saved output location/hash instead of repeating its full JSON')
    parser.add_argument('command', choices=[*FIELDS, 'schema'])
    parser.add_argument('--input', help='Exact host-authored JSON file, or - for stdin')
    parser.add_argument('--for-command', choices=sorted(FIELDS))
    parser.add_argument('--entities', nargs='+', help='Complete explicitly selected canonical schemas, with the authoring input contract')
    args = parser.parse_args(argv)
    if args.command == 'schema':
        if not args.for_command or args.input:
            parser.error('schema needs --for-command and no input')
        try:
            output = input_contract(args.for_command, args.entities)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(output, ensure_ascii=False, separators=(',', ':')))
        return 0
    if not args.input or not args.run or args.for_command or args.entities:
        parser.error('authoring needs --run and --input; --for-command is schema-only')
    try:
        state, records = _locations(args.state, args.records)
    except ValueError as exc:
        print(json.dumps({'error':type(exc).__name__, 'message':str(exc), 'applied':False}), file=sys.stderr)
        return 2
    record = records/uuid.uuid4().hex
    record.mkdir(parents=True, exist_ok=False)
    _write(record/'invocation.json', {'command':args.command, 'run_id':args.run,
        'state':str(state), 'input_source':args.input})
    stage = 'read-input'
    try:
        raw = sys.stdin.buffer.read() if args.input == '-' else Path(args.input).read_bytes()
        with (record/'input.json').open('xb') as stream:
            stream.write(raw)
        stage = 'parse-input'
        payload = _parse(raw)
        if args.command == 'finish' and type(payload) is dict and 'result_file' in payload:
            _exact(payload, FIELDS['finish']-{'result'}|{'result_file'}, 'finish')
            stage = 'resolve-result-file'
            raw_result, result = _result_file(payload['result_file'])
            with (record/'resolved-result.json').open('xb') as stream:
                stream.write(raw_result)
            payload = {key:value for key,value in payload.items() if key != 'result_file'} | {'result':result}
        stage = 'execute'
        output = execute(HostIO(state, args.run), args.command, payload)
        stage = 'save-output'
        path = record/'output.json'
        _write(path, output)
        receipt = {'record_dir':str(record), 'output_file':str(path),
            'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(json.dumps(receipt if args.receipt_only else {**receipt, 'output':output},
            ensure_ascii=False, allow_nan=False, separators=(',', ':')))
        return 0
    except (HostError, ValueError, KeyError, TypeError, OSError) as exc:
        error = {'error':type(exc).__name__, 'message':str(exc), 'stage':stage,
            'state_effect':'unknown; inspect saved state before retry', 'record_dir':str(record)}
        if isinstance(exc, HostError):
            error.update(command=exc.command, returncode=exc.returncode,
                stdout=exc.stdout, stderr=exc.stderr, detail=exc.detail)
        elif getattr(exc, 'details', None):
            error['detail'] = exc.details
        try:
            _write(record/'error.json', error)
        except OSError as storage_error:
            error['recording_error'] = str(storage_error)
        print(json.dumps(error, ensure_ascii=False, separators=(',', ':')), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
