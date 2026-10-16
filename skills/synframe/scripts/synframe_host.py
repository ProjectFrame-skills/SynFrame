"""Thin host I/O: no model, action selection, evidence labels or Review answers.

All judgments and real observations are supplied by the calling host. This
helper only addresses the adjacent installed CLI, reads state, and serializes
information-need feedback. Test drivers using prewritten judgments are fixtures.
"""
import json
import hashlib
import subprocess
import sys
import uuid
from copy import deepcopy
from html import escape
from pathlib import Path

from synframe_core.schema import META, PACKAGE_FIELDS, ports, validate_result_shape, validate_completion, ref
from synframe_core.files import file_sha256


def read_contract(root, name=None, offset=0, limit=6000, expected_sha=None, *, retained=None):
    """Bounded exact text delivery, never a claim that the host understood it.

    The limit is a transport size, not a learning/search/depth quota.
    A caller with a smaller output budget must request a smaller chunk.
    """
    root = Path(root).resolve()
    files = [root/'SKILL.md', *sorted((root/'references').glob('*.md'))]
    catalog = {str(p.relative_to(root)):p for p in files}
    if name is None:
        entries = []
        for name,path in catalog.items():
            raw = path.read_bytes()
            entries.append({'name':name, 'sha256':hashlib.sha256(raw).hexdigest(),
                            'characters':len(raw.decode('utf-8'))})
        return {'files':entries,
                'transport': {'unit':'Unicode characters', 'min_limit':1, 'max_limit':6000,
                              'default_limit':6000, 'continuation':'next_offset; use the current file sha256'},
                'scope':'Inventory only; follow SKILL.md loading conditions and read required text, not just this manifest'}
    if name not in catalog:
        raise ValueError('unknown bundled contract')
    raw = catalog[name].read_bytes(); checksum = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and expected_sha != checksum:
        raise ValueError('contract changed; restart this file read against its current identity')
    content = raw.decode('utf-8')
    if type(offset) is not int or not 0 <= offset <= len(content) or type(limit) is not int or not 1 <= limit <= 6000:
        raise ValueError('invalid character offset or transport limit (1..6000)')
    end = min(offset+limit,len(content)); chunk = content[offset:end]
    if retained is not None:
        if (type(retained) is not dict or set(retained) != {'retained_in_current_context','ranges'}
                or retained['retained_in_current_context'] is not True or type(retained['ranges']) is not list):
            raise ValueError('retained ranges require explicit actual retention in current context; clear after context loss')
        ranges = []
        for receipt in retained['ranges']:
            if type(receipt) is not dict or not {'name','sha256','offset','end','chunk_sha256'} <= set(receipt):
                raise ValueError('retained range needs exact delivery name/hash/bounds/chunk hash')
            if receipt['name'] != name or receipt['sha256'] != checksum:
                continue  # Old file identity cannot suppress current text.
            start,stop = receipt['offset'],receipt['end']
            if (type(start) is not int or type(stop) is not int or not 0 <= start <= stop <= len(content)
                    or hashlib.sha256(content[start:stop].encode('utf-8')).hexdigest() != receipt['chunk_sha256']):
                raise ValueError('retained range does not match delivered bytes')
            ranges.append((start,stop))
        covered = offset
        for start,stop in sorted(ranges):
            if start <= covered:
                covered = max(covered,stop)
        if covered >= end and end > offset:
            return {'name':name,'sha256':checksum,'offset':offset,'end':end,
                'characters':len(content),'next_offset':end if end<len(content) else None,
                'text':'','reused_retained':True,
                'scope':'Host explicitly declared current-context retention; no new reading or understanding proven. Clear retention after loss/truncation.'}
    return {'name':name, 'sha256':checksum, 'offset':offset, 'end':end,
            'characters':len(content), 'next_offset':end if end<len(content) else None,
            'text':chunk, 'chunk_sha256':hashlib.sha256(chunk.encode('utf-8')).hexdigest(),
            'scope':'Exact delivered text only; host must notice tool truncation and actually read it'}


class HostError(RuntimeError):
    """Keep machine-readable rejection and original output for repair/history."""
    def __init__(self, command, result):
        self.command = command
        self.returncode = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr
        self.detail = None
        for raw in (result.stderr, result.stdout):
            try:
                self.detail = json.loads(raw)
                break
            except ValueError:
                pass
        super().__init__(result.stderr or result.stdout or f'{command} exited {result.returncode}')


class HostIO:
    def __init__(self, state, run_id=None):
        self.state = str(Path(state).resolve())
        self.run_id = run_id
        self.cli = Path(__file__).with_name("synframe.py")

    def call(self, command, payload=None, **options):
        if 'input' in options:
            if not isinstance(options['input'], (str, Path)):
                raise ValueError('HostIO.call input= requires a CLI JSON file path or "-", not '
                    + type(options['input']).__name__
                    + '; pass structured JSON as payload=... or the second positional argument')
            if payload is not None:
                raise ValueError('HostIO.call requires either structured payload or input= file path, not both')
        args = [sys.executable, str(self.cli), "--state", self.state, '--compact', command]
        if self.run_id is not None and command not in {'schema', 'learning-basis', 'compare', 'artifact', 'solve', 'read-contract', 'read-contracts'}:
            args += ["--run", self.run_id]
        if command == 'artifact' and 'path' in options:
            args.append(str(options.pop('path')))
        for key, value in options.items():
            args += ["--" + key.replace("_", "-")]
            args += [str(v) for v in value] if isinstance(value,(list,tuple)) else [str(value)]
        if payload is not None:
            args += ["--input", "-"]
        result = subprocess.run(args, input=None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',',':'), allow_nan=False),
                                text=True, capture_output=True)
        if result.returncode:
            raise HostError(command, result)
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise HostError(command, result) from exc

    def start(self, goal, parent_run=None):
        # solve has no --run. Keep goal and actual environment/resources host-owned.
        if self.run_id is not None:
            raise ValueError("HostIO already has a run; inspect/resume it")
        options = {"parent_run": parent_run} if parent_run else {}
        run = self.call("solve", goal, **options)
        self.run_id = run["id"]
        return run

    def schemas(self, *entities):
        """Bundle explicitly chosen complete schema queries within caller's output budget."""
        if not entities:
            raise ValueError('schemas needs explicit entity names')
        return self.call('schema',entities=entities)['entities']

    def begin(self, action, judgment, intent, *, input_refs=None, evidence_refs=None, key=None):
        # Host must read observe and make its judgment against that observation.
        # Never stamp a stale/prewritten judgment with a newly fetched digest.
        observation = judgment["ddc"]["observable_state"]
        return self.call("intent", {"action": action, "observed_revision": observation["revision"],
            "input_refs": input_refs or [], "constraints": judgment["ddc"]["constraints"],
            "evidence_refs": evidence_refs or [], "decision": judgment, "intent": intent,
            "idempotency_key": key or uuid.uuid4().hex})

    def finish(self, operation, result):
        validate_result_shape(result)
        return self.call("finish", result, operation=operation["id"])

    def preserve_observation(self, operation, artifacts, *, expected_revision=None):
        if expected_revision is None:
            expected_revision = operation['extensions']['expected_apply_revision']
        return self.call("observe-result", artifacts, operation=operation["id"], expected=expected_revision)

    def preserve_files(self, operation, files, *, expected_revision=None):
        """Host supplies (path, source) pairs; hash actual bytes, not claims.

        EvidenceRecord.source must explicitly use the returned receipt's path
        or source. Preservation does not generate or verify the evidence claim.
        """
        artifacts = []
        for item in files:
            if type(item) is dict:
                if set(item) != {'path','source'}:
                    raise ValueError('observation file record needs exactly path/source')
                filename, source = item['path'], item['source']
            elif isinstance(item, (tuple,list)) and len(item) == 2:
                filename, source = item
            else:
                raise ValueError('observation file needs (path, source) or a path/source record')
            if not isinstance(filename,(str,Path)) or type(source) is not str or not source.strip():
                raise ValueError('observation needs an explicit path and nonempty source')
            path = Path(filename).expanduser().resolve()
            artifacts.append({'path': str(path), 'source': source,
                'sha256': file_sha256(path)})
        return self.preserve_observation(operation, artifacts, expected_revision=expected_revision)

    @staticmethod
    def write_package(contents, *, path, format, source):
        """Render every explicitly authored package value; no judgments or state writes.

        This exclusive-create artifact receipt does not adopt or complete a run.
        The host chooses an authorized path, actual source and explicit format.
        """
        if type(contents) is not dict or set(contents) != PACKAGE_FIELDS:
            raise ValueError('write_package needs all ten explicitly authored SolutionPackage.contents fields')
        if format not in {'html', 'json'} or type(source) is not str or not source.strip():
            raise ValueError('write_package needs an explicit html/json format and nonempty source')
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ValueError('write_package needs an explicit output file path')

        def validate(value):
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    raise ValueError('package JSON object keys must be strings')
                for item in value.values(): validate(item)
            elif type(value) is list:
                for item in value: validate(item)
            elif value is not None and type(value) not in {str, int, float, bool}:
                raise ValueError('package values must be JSON objects, lists, strings, numbers, booleans or null')
        validate(contents)
        serialized = json.dumps(contents, ensure_ascii=False, allow_nan=False, indent=2) + '\n'

        def render(value):
            if type(value) is dict:
                return '<dl>' + ''.join('<dt>' + escape(key) + '</dt><dd>' + render(item)
                    + '</dd>' for key, item in value.items()) + '</dl>'
            if type(value) is list:
                return '<ul>' + ''.join('<li>' + render(item) + '</li>' for item in value) + '</ul>'
            kind = 'string' if type(value) is str else 'null' if value is None else 'boolean' if type(value) is bool else 'number'
            return '<pre data-json-type="' + kind + '">' + escape(value if type(value) is str else
                json.dumps(value, ensure_ascii=False, allow_nan=False)) + '</pre>'

        output = serialized if format == 'json' else (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>SynFrame Solution Package</title><style>'
            'body{font:16px/1.6 system-ui,sans-serif;max-width:70rem;margin:auto;padding:2rem}'
            'dt{font-weight:700;margin-top:1rem}dd{margin-left:1rem}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}'
            '</style></head><body>' + render(contents) + '</body></html>\n')
        destination = Path(path).expanduser().resolve()
        if destination.is_relative_to(Path(__file__).resolve().parents[1]):
            raise ValueError('package artifacts must be outside the installed skill')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(output)
        return {'path':str(destination), 'sha256':file_sha256(destination), 'source':source}

    @staticmethod
    def edit(document, **changes):
        """Copy a saved record into patch form without mutating its nested data.

        No enums, evidence, closure basis or references are silently repaired.
        """
        return deepcopy({**{k: v for k, v in document.items()
            if k not in META - {'id', 'type', 'provenance', 'validity_status'}}, **changes})

    @staticmethod
    def reference(document):
        return {'id': document['id'], 'revision': document['revision']}

    @staticmethod
    def edit_fields(document, *, expected_ref, replacements, removals):
        """Apply explicit dictionary-key edits to an exact retained document.

        Lists are whole values: no index edits, implicit merge or reference
        refresh. This serializes changes, not their semantic adequacy. A caller
        must still compare the base with current state before applying it.
        """
        ref(expected_ref)
        if HostIO.reference(document) != expected_ref:
            raise ValueError('field edits require the exact retained base reference')
        if type(replacements) is not list or type(removals) is not list:
            raise ValueError('field edits need explicit replacement and removal lists')
        paths = []
        for item in replacements:
            if type(item) is not dict or set(item) != {'path', 'value'}:
                raise ValueError('replacement needs exactly path/value')
            paths.append(item['path'])
        paths += removals
        reserved = META - {'provenance', 'validity_status'}
        for path in paths:
            if (type(path) is not list or not path
                    or any(type(key) is not str or not key for key in path)
                    or path[0] in reserved):
                raise ValueError('edit path needs dictionary keys and cannot change core metadata or identity')
        for i, path in enumerate(paths):
            if any(path[:len(other)] == other or other[:len(path)] == path for other in paths[:i]):
                raise ValueError('duplicate or overlapping edit paths')
        result = HostIO.edit(document)
        for path in paths:
            parent = result
            for key in path[:-1]:
                if type(parent) is not dict or key not in parent:
                    raise ValueError('edit parent does not exist')
                parent = parent[key]
            if type(parent) is not dict:
                raise ValueError('edit paths cannot traverse lists or scalar values')
        for item in replacements:
            parent = result
            for key in item['path'][:-1]:
                parent = parent[key]
            parent[item['path'][-1]] = deepcopy(item['value'])
        for path in removals:
            parent = result
            for key in path[:-1]:
                parent = parent[key]
            if path[-1] not in parent:
                raise ValueError('removal target does not exist')
            del parent[path[-1]]
        return result

    def patch_refs(self, changes):
        return self.call('patch-refs', changes)

    @staticmethod
    def patch_ref(identity):
        """Explicit reference to a record in this patch, resolved by build_result.

        Saved input/history references remain literal {id, revision} objects.
        This marker is not a stored reference and cannot refresh old judgments.
        """
        if type(identity) is not str or not identity.strip():
            raise ValueError('patch reference needs an explicit record ID')
        return {'$patch_ref': identity}

    @staticmethod
    def connect(source, output, target, input, *, evidence_refs):
        """Serialize explicitly selected ports; no inferred adapter or evidence."""
        ports(source['outputs']); ports(target['inputs'])
        outputs = {p['name']: p['type'] for p in source['outputs']}
        inputs = {p['name']: p['type'] for p in target['inputs']}
        if output not in outputs or input not in inputs:
            raise ValueError(f'unknown port; outputs={list(outputs)}, inputs={list(inputs)}')
        if outputs[output] != inputs[input]:
            raise ValueError(f'incompatible I/O types {outputs[output]} → {inputs[input]}')
        if type(evidence_refs) is not list or not evidence_refs:
            raise ValueError('connection needs explicit evidence references')
        def pointer(document):
            return (HostIO.reference(document) if 'revision' in document
                    else HostIO.patch_ref(document['id']))
        return deepcopy({'from_ref':pointer(source), 'output':output, 'to_ref':pointer(target),
                         'input':input, 'evidence_refs':evidence_refs})

    def review_context(self, candidate):
        return self.call('review-context', candidate=f"{candidate['id']}@{candidate['revision']}")

    def preflight(self, operation, result):
        return self.call('preflight', result, operation=operation['id'])

    def work_context(self, operation=None, *, document_ids=None):
        options = {'operation':operation['id']} if operation else {}
        if document_ids is not None:
            options['document_ids'] = document_ids
        return self.call('work-context', **options)

    @staticmethod
    def result_ref(applied_result, identity):
        """Use the actual returned version, never increment or refresh a judgment."""
        matches = [p for p in applied_result['result_refs'] if p['id'] == identity]
        if len(matches) != 1:
            raise ValueError('result_ref requires exactly one returned reference for the explicit ID')
        return deepcopy(ref(matches[0]))

    def gate(self, candidate_ref, review_ref):
        ref(candidate_ref); ref(review_ref)
        return self.call('gate', candidate=f"{candidate_ref['id']}@{candidate_ref['revision']}",
            review=f"{review_ref['id']}@{review_ref['revision']}")

    def complete(self, context, *, package_ref, reason, evidence_refs, verification):
        """Serialize explicit host checks against its retained work-context snapshot.

        No fresh-state stamping, PASS generation or minor-uncertainty labeling.
        The core still validates current revision, actual evidence, Commit,
        remaining obligations and artifacts before changing the run state.
        """
        validate_completion(verification, context['goal'])
        ref(package_ref)
        return self.call('transition', {'target':'COMPLETED','reason':reason,
            'evidence_refs':evidence_refs,'verification':verification,'package_ref':package_ref},
            expected=context['revision'])

    def build_result(self, operation, changes, *, result_ids, preserved_refs,
                     evidence_refs, unresolved_items, observed_effects, next_decision_inputs,
                     outcome, learning_results, propagation_resolutions, path_assessments,
                     expected_revision=None):
        """Serialize host decisions; do not default answers, feedback or success.

        Only explicitly requested changed IDs get projected result versions.
        Unchanged MAINTAIN results must be explicitly supplied as preserved_refs.
        Explicit patch_ref markers bind only IDs in changes; literal refs stay
        unchanged. Inspect resolved content and finalize closure basis afterward.
        This method does not apply anything; call finish then inspect work_context.
        """
        projection = self.patch_refs(changes)
        if expected_revision is not None and projection['observed_revision'] != expected_revision:
            raise ValueError('result projection changed after the host observation; reassess without automatic rebasing')
        projected = projection['refs']
        if len(set(result_ids)) != len(result_ids) or any(i not in projected for i in result_ids):
            raise ValueError('result_ids must identify explicit distinct patch records')
        result = {'operation_id':operation['id'], 'proposed_state_changes':changes,
            'result_refs':[projected[i] for i in result_ids]+preserved_refs,
            'evidence_refs':evidence_refs, 'unresolved_items':unresolved_items,
            'observed_effects':observed_effects, 'next_decision_inputs':next_decision_inputs,
            'outcome':outcome, 'learning_results':learning_results,
            'propagation_resolutions':propagation_resolutions, 'path_assessments':path_assessments}
        def bind(value):
            if type(value) is dict:
                if '$patch_ref' in value:
                    identity = value['$patch_ref']
                    if set(value) != {'$patch_ref'} or type(identity) is not str or identity not in projected:
                        raise ValueError('patch reference must identify exactly one explicit patch record')
                    return deepcopy(projected[identity])
                return {k:bind(v) for k,v in value.items()}
            if type(value) is list:
                return [bind(v) for v in value]
            return deepcopy(value)
        result = bind(result)
        validate_result_shape(result)
        return result
