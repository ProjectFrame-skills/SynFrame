"""§§27.8–27.10: deterministic responsibility identities and record bindings.

No tool search, applicability judgment, relevance score or semantic PASS lives
here. The host supplies those judgments and performs the actual observations.
"""
from pathlib import Path
import hashlib
from .files import file_sha256
from .schema import require, ContractError
from .graph import reference, verified
from .learning import validate_state


# Stable ability IDs identify adopted responsibilities, not search/depth quotas.
REQUIREMENTS = {
    'scope': [('applicability', 'Determine whether the original goal requires tool selection, use or composition')],
    'discovery': [
        ('goal_link', 'Connect discovery questions to goal capabilities'),
        ('actual_search', 'Provide actual observations searching beyond the incumbent candidate inventory'),
        ('observed_scope', 'Distinguish observed mechanisms and candidate scope from unexamined scope'),
        ('selection_effect', 'Assess effects on candidates, composition and remaining work'),
        ('termination', 'Ground termination in observations and remaining discriminating questions')],
    'composition': [
        ('roles', 'Assess goal roles of incumbent and discovered candidates'),
        ('dispositions', 'Ground candidate inclusion, scoped exclusion and deferral'),
        ('combinations', 'Assess relevant standalone, alternative, complementary and mixed compositions'),
        ('connections', 'Judge material I/O, prerequisites, transformations and execution actors'),
        ('comparison', 'Ground current candidate comparison and selection'),
        ('remaining_work', 'Preserve material gaps, followups and actual upward effects')],
}


def identity(goal_id, responsibility):
    require(responsibility in REQUIREMENTS, 'unknown tool responsibility')
    return goal_id + ':tool-' + responsibility


def seed(goal, responsibility, origin=None):
    """Register unanswered questions only. Never supply applicability or success."""
    pointer = reference(goal)
    return {'id': identity(goal['id'], responsibility), 'type': 'LearningTask',
        'goal_ref': pointer, 'question': 'Assess ' + responsibility + ' under adopted §§27.8–27.10 for: ' + goal['objective'],
        'subject': {'concept': 'Operating responsibility: tool ' + responsibility},
        'context': {'purpose': 'Preserve original goal and adopted tool responsibility',
            'environment': {}, 'version': 'v3.2 / §§27.8–27.10', 'conditions': [],
            'constraints': goal['explicit_constraints'], 'scope': 'Current goal; host must assess actual applicability and observations'},
        'origin_refs': [origin or pointer], 'goal_connections': [{'goal_ref': pointer,
            'facet_ids': [f['id'] for f in goal['extensions']['goal_alignment']['facets']],
            'path_refs': [origin] if origin else [], 'rationale': 'Operating-contract obligation, not an invented user quotation'}],
        'answer_requirements': [{'id': responsibility + '.' + key, 'ability': ability,
            'discriminator': 'Observe current goal, relevant sources and actual work within this responsibility',
            'sufficient_when': 'Host grounds this contextual ability with claim-specific observations and scope',
            'evidence_requirement': 'Current evidence; intent or a label alone is insufficient'}
            for key, ability in REQUIREMENTS[responsibility]],
        'assessment': {'relevance': 'UNASSESSED' if responsibility == 'scope' else 'RELEVANT',
            'materiality': 'UNKNOWN' if responsibility == 'scope' else 'MATERIAL',
            'role': 'SCOPING' if responsibility == 'scope' else 'SELECTION',
            'rationale': 'Host applicability assessment pending' if responsibility == 'scope' else 'Applicable contract responsibility must actually be fulfilled',
            'evidence_refs': [], 'unknowns': ['Actual answer and required observations']},
        'answer': {'status': 'UNANSWERED', 'claims': [], 'counterevidence_refs': [], 'gaps': [],
            'scope': 'Unassessed operating obligation'},
        'understanding': {'status': 'UNASSESSED', 'abilities': [], 'k_level': None},
        'expansion': {'status': 'UNASSESSED', 'discoveries': [], 'scope_rationale': 'Not yet observed or evaluated', 'evidence_refs': []},
        'dependency_refs': [], 'work_state': 'READY', 'disposition': 'OPEN', 'closure_assessment': {},
        'reopen_conditions': [], 'extensions': {'next_action': 'EXPAND_COMPOSITION' if responsibility == 'composition' else 'DISCOVER_KNOWLEDGE'}}


def terminal(task, resolve):
    seen = set()
    while task['disposition'] == 'MERGED' or task.get('closure_assessment', {}).get('verdict') in {'REUSED', 'SUPERSEDED'}:
        require(task['id'] not in seen, 'tool obligation reuse cycle')
        seen.add(task['id'])
        validate_state(task, resolve)
        task = resolve(task['closure_assessment']['target_ref'])
    return task


def applicable(scope, resolve):
    if scope is None:
        return None
    try:
        actual = terminal(scope, resolve)
        if actual['disposition'] != 'CLOSED':
            return None
        verdict = actual['closure_assessment'].get('verdict')
        return True if verdict == 'ANSWERED' else False if verdict == 'NOT_APPLICABLE' else None
    except (ContractError, KeyError):
        return None


def registration_changes(goal, documents, resolve):
    """Once the host declares applicability, retain unanswered duties in state."""
    docs = {d['id']: d for d in documents}
    scope = docs.get(identity(goal['id'], 'scope'))
    if scope is None or scope['goal_ref'] != reference(goal) or applicable(scope, resolve) is not True:
        return []
    changes = [seed(goal, role, reference(scope)) for role in ('discovery', 'composition')
               if identity(goal['id'], role) not in docs]
    discovery = docs.get(identity(goal['id'], 'discovery'))
    pointer = reference(discovery) if discovery else {'id': identity(goal['id'], 'discovery'), 'revision': 1}
    for task in changes:
        if task['id'] == identity(goal['id'], 'composition'):
            task['dependency_refs'] = [{'source_ref':pointer, 'role':'COMPARES_USING', 'required':False,
                'scope':'Final composition must consume current discovery results',
                'rationale':'Discovery and composition can interleave; final selection must reflect actual current discoveries'}]
    return changes


def validate_identity(task, goal, resolve):
    role = next((role for role in REQUIREMENTS if task['id'] == identity(goal['id'], role)), None)
    if role is None:
        return
    require(task['goal_ref'] == reference(goal), 'tool obligation uses an old goal')
    require(task['assessment']['role'] == ('SCOPING' if role == 'scope' else 'SELECTION'),
            'contractual tool obligation cannot become an independent improvement')
    if role != 'scope':
        require(task['assessment']['relevance'] == 'RELEVANT' and task['assessment']['materiality'] == 'MATERIAL',
                'contractual tool obligation cannot be downgraded or excluded')
    actual = terminal(task, resolve) if task['disposition'] in {'CLOSED', 'MERGED'} else task
    ids = {need['id'] for need in actual['answer_requirements']}
    require({role + '.' + key for key, _ in REQUIREMENTS[role]} <= ids,
            'tool obligation lost a required ability or merged responsibility')
    if actual['disposition'] == 'CLOSED':
        require(actual['goal_ref'] == reference(goal), 'reused obligation uses an old goal')
        require(actual['answer']['status'] == 'SUPPORTED' and actual['understanding']['status'] == 'SUFFICIENT'
                and actual['expansion']['status'] == 'ACCOUNTED', 'tool obligation lacks actual supported assessment: ' + role)
        verdict = actual['closure_assessment']['verdict']
        if role == 'scope':
            require(verdict in {'ANSWERED','NOT_APPLICABLE'}, 'tool applicability needs an explicit applicable/nonapplicable result')
            require(actual['assessment']['relevance'] == ('RELEVANT' if verdict == 'ANSWERED' else 'NOT_RELEVANT'),
                    'tool applicability verdict contradicts declared relevance')
            require(actual['assessment']['materiality'] == ('MATERIAL' if verdict == 'ANSWERED' else 'NONMATERIAL'),
                    'tool applicability verdict contradicts declared materiality')
        else:
            require(verdict == 'ANSWERED', 'applicable tool duty cannot close as nonapplicable')
        if role == 'composition':
            connections = [d for d in actual['dependency_refs'] if d['role'] == 'COMPARES_USING'
                and d['source_ref']['id'] == identity(goal['id'], 'discovery')]
            require(connections, 'final composition must bind current discovery results')
            discovery = resolve(connections[0]['source_ref'])
            require(terminal(discovery,resolve)['disposition'] == 'CLOSED',
                    'final composition cannot omit unfinished discovery; work may interleave before closure')


def observation_binding(task, operations, resolve):
    """Require actual-search ability evidence to reach preserved raw observations.

    File/hash/operation bindings prove recorded work, never relevance or truth.
    EvidenceRecord.source is the actual receipt path or its original source.
    """
    ability = next((a for a in task['understanding']['abilities'] if a['id'] == 'discovery.actual_search'), None)
    if not ability or ability['status'] != 'MET':
        return False
    evidence = [resolve(p) for p in ability['evidence_refs']]
    allowed_tasks = {task['id']}
    queue = [task]
    while queue:
        owner = queue.pop()
        for dep in owner['dependency_refs']:
            if dep['role'] not in {'ANSWER_DEPENDS_ON', 'SUPPORTS', 'USES_PROOF', 'REUSES'}:
                continue
            provider = resolve(dep['source_ref'])
            if provider['type'] == 'LearningTask' and provider['id'] not in allowed_tasks:
                allowed_tasks.add(provider['id']); queue.append(provider)
    for operation in operations:
        if operation['action'] != 'DISCOVER_KNOWLEDGE' or not operation['applied'] or operation['result'].get('outcome') != 'SUCCEEDED':
            continue
        selected = operation['intent'].get('learning_task_refs', [])
        if not any(p['id'] in allowed_tasks for p in selected):
            continue
        for receipt in operation['extensions'].get('actual_observations', []):
            path = Path(receipt['path'])
            if not path.is_file() or file_sha256(path) != receipt['sha256']:
                continue
            if any(e['source'] in {receipt['source'], receipt['path']} for e in evidence):
                return True
    return False


def gate_errors(goal, documents, operations, resolve):
    docs = {d['id']: d for d in documents}
    errors = []
    scope = docs.get(identity(goal['id'], 'scope'))
    if scope is None:
        return ['missing tool applicability responsibility']
    state = applicable(scope, resolve)
    required = ['scope'] + (['discovery', 'composition'] if state is True else [])
    if state is None:
        errors.append('tool applicability is unresolved')
    for role in required:
        task = docs.get(identity(goal['id'], role))
        if task is None:
            errors.append('missing contractual tool obligation: ' + role); continue
        try:
            require(task['validity_status'] == 'VALID', 'tool obligation is stale')
            validate_identity(task, goal, resolve)
            validate_state(task, resolve, goal=goal,
                discovery_resolve=lambda p: resolve(reference(docs[p["id"]])))
            actual = terminal(task, resolve)
            require(actual['goal_ref'] == reference(goal), 'reused obligation uses an old goal')
            require(actual['disposition'] == 'CLOSED' and actual['work_state'] == 'IDLE', 'unfinished tool obligation: ' + role)
            require(actual['answer']['status'] == 'SUPPORTED' and actual['understanding']['status'] == 'SUFFICIENT'
                    and actual['expansion']['status'] == 'ACCOUNTED', 'tool obligation lacks actual supported assessment: ' + role)
            for key, _ in REQUIREMENTS[role]:
                ability = next((a for a in actual['understanding']['abilities'] if a['id'] == role+'.'+key), None)
                require(ability and ability['status'] == 'MET' and verified(ability['evidence_refs'], resolve), 'unmet tool ability: '+role+'.'+key)
            if role != 'scope':
                require(actual['closure_assessment']['verdict'] == 'ANSWERED', 'applicable tool duty cannot close as nonapplicable')
            if role == 'discovery':
                require(observation_binding(actual, operations, resolve), 'tool discovery has no preserved actual-search observation binding')
            if role == 'composition':
                require(composition_binding(actual, operations), 'tool composition has no actual current assessment operation')
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    return errors


def composition_binding(task, operations):
    return any(op['action'] == 'EXPAND_COMPOSITION' and op['applied']
        and op['result'].get('outcome') == 'SUCCEEDED'
        and any(record.get('result_ref') == reference(task) and record.get('observations')
                and record.get('upward_effects') for record in op['result'].get('learning_results', []))
        for op in operations)


def projection(goal, documents, resolve):
    docs = {d['id']: d for d in documents}
    scope = docs.get(identity(goal['id'], 'scope'))
    state = applicable(scope, resolve) if scope and scope['goal_ref'] == reference(goal) and scope['validity_status']=='VALID' else None
    roles = ['scope'] + (['discovery', 'composition'] if state is True else [])
    return {'applicable': state, 'required': [{'responsibility': role,
        'expected_id': identity(goal['id'], role), 'task_ref': reference(docs[identity(goal['id'], role)])
        if identity(goal['id'], role) in docs else None} for role in roles],
        'semantic_scope': 'Host applicability and sufficiency judgments; core exposes identities and bindings'}
