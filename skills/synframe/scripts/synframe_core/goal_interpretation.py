"""§§27.11–27.12: expected goal review and two independently bound paths.

These checks establish records/current references, not semantic entailment,
view completeness, hidden intent, counterfactual quality or useful advice.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
from .files import file_sha256
from .schema import require, ContractError, META
from .graph import reference, verified
from .learning import nonempty, validate_state
from .tool_obligations import seed as operating_seed, terminal

REQUIREMENTS = [
    ('source_preservation', 'Distinguish explicit outcome/means/constraints from inferred requirements'),
    ('result_properties', 'Distinguish relevant use, scope, preservation, transformation and reuse conditions'),
    ('material_views', 'Derive source-grounded material views or ground sufficiency of the current interpretation'),
    ('differences', 'Assess effects of interpretation differences on function, selection, work and verification'),
    ('uncertainty', 'Distinguish observed technical facts from unresolved intent, preference and authority'),
    ('consumption', 'Verify actual downstream changes or grounded maintenance'),
    ('termination', 'Ground bounded termination and material reopening conditions')]


def identity(goal_id):
    return goal_id + ':goal-interpretation'


def seed(goal):
    task = operating_seed(goal, 'scope')
    task.update(id=identity(goal['id']), question='Assess source-goal interpretation support AND material-view omission under §§27.11–27.12: ' + goal['objective'],
        subject={'concept': 'Operating responsibility: goal interpretation review'})
    task['context'].update(purpose='Preserve source outcome without narrowing or inventing intent',
        version='v3.2 / §§27.11–27.12', scope='Current goal; initial interpretation remains provisional')
    task['answer_requirements'] = [{'id': 'interpretation.'+key, 'ability': ability,
        'discriminator':'Compare raw request/context/result use with current interpretation; assess support and omissions separately',
        'sufficient_when':'Host grounds this ability in actual comparisons, scoped processing and downstream effects',
        'evidence_requirement':'Claim-specific current observations; positive method evidence alone is not omission review'}
        for key,ability in REQUIREMENTS]
    task['assessment']['rationale'] = 'Goal interpretation review is required; actual support and omission assessments pending'
    task['assessment']['unknowns'] = ['Source preservation, result properties, material differences, downstream processing']
    return task


def _path(path, facets, resolve, name):
    require(type(path) is dict, 'missing independent interpretation path: '+name)
    for key in ('target','scope','source_locator','rationale'):
        nonempty(path.get(key), name+' '+key)
    require(set(path.get('facet_ids',[])) == facets, name+' path lost source facets')
    require(verified(path.get('evidence_refs',[]),resolve), name+' path needs current evidence')


def validate_identity(task, goal, resolve):
    if task['id'] != identity(goal['id']):
        return
    require(task['goal_ref'] == reference(goal), 'interpretation review uses an old goal')
    require(task['assessment']['role'] == 'SCOPING', 'interpretation review cannot become an independent improvement')
    require(task['assessment']['relevance'] != 'NOT_RELEVANT' and task['assessment']['materiality'] != 'NONMATERIAL',
        'required interpretation review cannot be excluded')
    actual = terminal(task,resolve) if task['disposition'] in {'CLOSED','MERGED'} else task
    require({'interpretation.'+key for key,_ in REQUIREMENTS} <= {n['id'] for n in actual['answer_requirements']},
        'interpretation review lost required abilities')
    if actual['disposition'] != 'CLOSED':
        return
    require(actual['goal_ref'] == reference(goal) and actual['closure_assessment']['verdict']=='ANSWERED',
        'interpretation review needs current answered assessment, not nonapplicability')
    require(actual['answer']['status']=='SUPPORTED' and actual['understanding']['status']=='SUFFICIENT'
        and actual['expansion']['status']=='ACCOUNTED', 'interpretation review lacks supported assessment')
    review=actual.get('extensions',{}).get('interpretation_review',{})
    facets={f['id'] for f in goal['extensions']['goal_alignment']['facets']}
    for name in ('support','omission'):
        _path(review.get(name),facets,resolve,name)
    support,omission=review['support'],review['omission']
    require((support['target'],support['source_locator']) != (omission['target'],omission['source_locator']),
        'positive support cannot substitute for the omission comparison')
    # Same source/evidence may support both paths, but the actual comparison
    # target and located processing must remain independently inspectable.
    for key in ('source_to_result','result_to_source','counterfactual_scope','observed_structures','remaining_uncertainty_assessment'):
        nonempty(omission.get(key),'omission '+key)
    require(type(omission.get('difference_ids')) is list, 'omission must identify assessed differences, possibly none')
    discoveries={d['id']:d for d in actual['expansion']['discoveries']}
    require(set(omission['difference_ids']) <= set(discoveries), 'omission differences need canonical discovery processing')
    require(all(discoveries[i]['assessment'] not in {'UNKNOWN','UNASSESSED'} for i in omission['difference_ids']),
        'interpretation closure retains an unassessed important difference')
    require(review.get('handling') in {'CURRENT','COMMON','CONDITIONAL'}, 'interpretation processing remains unresolved')
    if review['handling']=='CONDITIONAL':
        require(review.get('conditional_results'), 'conditional treatment needs actual branch constructions')
    for key in ('current_interpretation','assumptions','result_properties','treatment','termination_scope'):
        nonempty(review.get(key),'interpretation '+key)
    interpretations=review.get('interpretations')
    require(type(interpretations) is list and interpretations,'interpretation review needs stable source-grounded interpretation records')
    ids=set()
    for item in interpretations:
        nonempty(item.get('id'),'interpretation stable ID')
        require(item['id'] not in ids,'duplicate interpretation ID');ids.add(item['id'])
        require(item.get('facet_ids') and set(item['facet_ids']) <= facets,'interpretation lost source connection')
        for key in ('result_scope','basis','assumptions','difference','decision_impact','uncertainties','disposition','rationale','reopen_condition'):
            nonempty(item.get(key),'interpretation '+key)
        require(item.get('consumer_refs'),'interpretation needs actual consumers')
        for p in item['consumer_refs']: resolve(p)
    require(type(review.get('conditional_results',[])) is list,'conditional results must be scoped records')
    for branch in review.get('conditional_results',[]):
        for key in ('condition','result','method','roles','work','verification','fact_assessment','unresolved_preference_authority'):
            nonempty(branch.get(key),'conditional '+key)
        require(verified(branch.get('evidence_refs',[]),resolve),'conditional construction needs actual grounds')
    effects=review.get('effects')
    require(type(effects) is list and effects,'interpretation result needs actual consumer effects')
    for effect in effects:
        resolve(effect['target_ref'])
        require(effect.get('assessment') in {'MAINTAIN','REVISE','INVALIDATE','NEEDS_OBSERVATION'},'invalid interpretation consumer assessment')
        nonempty(effect.get('rationale'),'interpretation effect rationale')
        require(verified(effect.get('evidence_refs',[]),resolve),'interpretation effect needs current evidence')
        require(effect['assessment']!='NEEDS_OBSERVATION','interpretation closure retains unprocessed consumer effects')


def assessment_content(task):
    """Only consumer links/effects and their closure snapshot may be rebound.

    Keep goal, question, abilities, claims, K, both comparison paths and all
    other content exact. A rebind is not a new learning result.
    """
    content = deepcopy({k:v for k,v in task.items() if k not in META - {'provenance'}})
    content.setdefault('provenance', [])
    review = content.get('extensions', {}).get('interpretation_review', {})
    for item in review.get('interpretations', []):
        item.pop('consumer_refs', None)
    review.pop('effects', None)
    for key in ('basis', 'rationale'):
        content.get('closure_assessment', {}).pop(key, None)
    return content


def validate_rebinding(previous, task):
    require(previous['disposition'] == task['disposition'] == 'CLOSED'
        and previous['work_state'] == task['work_state'] == 'IDLE',
        'interpretation rebinding requires an already closed idle assessment')
    require(assessment_content(previous) == assessment_content(task),
        'interpretation rebinding changed knowledge/scope; perform material reassessment')
    old = previous['extensions']['interpretation_review']
    new = task['extensions']['interpretation_review']
    for before, after in zip(old['interpretations'], new['interpretations']):
        require({p['id'] for p in before['consumer_refs']} == {p['id'] for p in after['consumer_refs']},
            'interpretation rebinding cannot replace consumer roles')
    require({e['target_ref']['id'] for e in old['effects']} == {e['target_ref']['id'] for e in new['effects']},
        'interpretation rebinding cannot omit consumer effects')
    require(all(e['assessment'] == 'MAINTAIN' for e in new['effects']),
        'interpretation rebinding only records grounded current consumption; changes need their actual operation')


def _fresh_consumption(task, op, operations, resolve):
    """Fresh located consumer comparison, separate from preserved learning."""
    consumers = {p['id']:p for i in task['extensions']['interpretation_review']['interpretations']
                 for p in i['consumer_refs']}
    consumers.update({e['target_ref']['id']:e['target_ref']
                      for e in task['extensions']['interpretation_review']['effects']})
    earlier = [o for o in operations if o['id'] != op['id'] and
               o['extensions']['expected_apply_revision'] < op['extensions']['expected_apply_revision']]
    earlier_paths = {r['path'] for o in earlier
                     for r in o['extensions'].get('actual_observations', [])}
    earlier_hashes = {r['sha256'] for o in earlier
                      for r in o['extensions'].get('actual_observations', [])}
    changed = {d['id'] for d in op['result'].get('proposed_state_changes', []) if d['type'] == 'EvidenceRecord'}
    grounds = []
    for pointer in op['result'].get('evidence_refs', []):
        doc = resolve(pointer)
        comparison = doc.get('extensions', {}).get('consumer_comparison', {})
        if (doc['id'] not in changed or doc.get('observation_kind') != 'measured'
            or comparison.get('consumer_refs') != sorted(consumers.values(), key=lambda p:p['id'])
            or type(comparison.get('rationale')) is not str or not comparison['rationale'].strip()
            or comparison.get('assessment') != 'MAINTAIN'):
            continue
        if any(receipt['path'] not in earlier_paths and receipt['sha256'] not in earlier_hashes
            and doc['source'] in {receipt['path'],receipt['source']}
            and Path(receipt['path']).is_file()
            and file_sha256(Path(receipt['path'])) == receipt['sha256']
            for receipt in op['extensions'].get('actual_observations', [])):
            grounds.append(pointer)
    return bool(grounds) and all(any(p in grounds for p in effect['evidence_refs'])
        for effect in task['extensions']['interpretation_review']['effects'])


def observation_binding(task, operations, resolve, *, allow_rebinding=True):
    """Bind both located paths to real preserved work, not a plan or free link."""
    review=task.get('extensions',{}).get('interpretation_review',{})
    for name in ('support','omission'):
        path=review.get(name,{})
        evidence=[resolve(p) for p in path.get('evidence_refs',[])]
        bound=False
        for op in operations:
            if not op['applied'] or op['result'].get('outcome')!='SUCCEEDED':continue
            records=[r for r in op['result'].get('learning_results',[]) if r.get('result_ref')==reference(task)]
            if not records or not any(r.get('observations') and r.get('upward_effects') for r in records):continue
            changed={c['id'] for c in op['result'].get('proposed_state_changes',[])}
            if any(e['assessment'] in {'REVISE','INVALIDATE'} and (e['target_ref']['id'] not in changed
                or e['target_ref'] not in op['result']['result_refs']) for e in review.get('effects',[])):continue
            for receipt in op['extensions'].get('actual_observations',[]):
                raw=Path(receipt['path'])
                if (raw.is_file() and file_sha256(raw)==receipt['sha256']
                    and any(e['source'] in {receipt['source'],receipt['path']} for e in evidence)):
                    bound=True
        if not bound and allow_rebinding:
            # A new current consumer comparison can preserve an unchanged,
            # originally observed assessment. Never invent learning progress or
            # treat a copied closure as a fresh support/omission comparison.
            for op in operations:
                intent = op['intent'].get('interpretation_rebind', {})
                if (not op['applied'] or op['result'].get('outcome') != 'SUCCEEDED'
                    or op['action'] != 'SIMPLIFY' or not intent.get('rationale')
                    or intent.get('task_ref', {}).get('id') != task['id']
                    or intent['task_ref']['revision'] >= task['revision']
                    or reference(task) not in op['result'].get('result_refs', [])
                    or not _fresh_consumption(task, op, operations, resolve)):
                    continue
                for source_op in operations:
                    for old in source_op['result'].get('proposed_state_changes', []) if source_op.get('result') else []:
                        if (old['id'] != task['id'] or old.get('disposition') != 'CLOSED'
                            or assessment_content(old) != assessment_content(task)):
                            continue
                        pointers = [r['result_ref'] for r in source_op['result'].get('learning_results', [])
                                    if r['result_ref']['id'] == task['id']]
                        if not pointers: continue
                        original = {**old, 'revision': pointers[0]['revision']}
                        try:
                            observation_binding(original, operations, resolve, allow_rebinding=False)
                        except ContractError:
                            continue
                        bound = True
                if bound: break
        require(bound,'interpretation '+name+' lacks preserved actual comparison binding')
    return True


def gate_errors(goal,documents,operations,resolve):
    docs={d['id']:d for d in documents}
    task=docs.get(identity(goal['id']))
    if task is None:return ['missing expected goal interpretation review responsibility']
    try:
        require(task['validity_status']=='VALID','interpretation review is stale')
        validate_identity(task,goal,resolve)
        validate_state(task,resolve,goal=goal,discovery_resolve=lambda p:resolve(reference(docs[p['id']])))
        actual=terminal(task,resolve)
        require(actual['disposition']=='CLOSED' and actual['work_state']=='IDLE','unfinished goal interpretation review')
        observation_binding(actual,operations,resolve)
    except (ContractError,KeyError,TypeError,ValueError) as exc:return [str(exc)]
    return []


def projection(goal,documents):
    task=next((d for d in documents if d['id']==identity(goal['id'])),None)
    review=(task or {}).get('extensions',{}).get('interpretation_review',{})
    return {'expected_id':identity(goal['id']),'task_ref':reference(task) if task else None,
        'current_goal':bool(task and task['goal_ref']==reference(goal) and task['validity_status']=='VALID'),
        'answer_state':task['answer']['status'] if task else 'UNANSWERED',
        'support_recorded':bool(review.get('support')),'omission_recorded':bool(review.get('omission')),
        'semantic_scope':'Presence/current binding only; host must judge source preservation, counterfactual scope and materiality'}
