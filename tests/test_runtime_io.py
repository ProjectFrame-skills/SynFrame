"""Serialization/transaction fixtures, never autonomous reasoning evidence."""
import copy
import json
import subprocess
import sys
import unittest

import test_core as fixtures
from test_core import evidence, asset, r, output, ContractError
from test_learning import task
from synframe_core.schema import schema_catalog
from synframe_host import HostIO, HostError


class RuntimeIOAcceptance(unittest.TestCase):
    setUp = fixtures.CoreAcceptance.setUp
    tearDown = fixtures.CoreAcceptance.tearDown
    revision = fixtures.CoreAcceptance.revision
    request = fixtures.CoreAcceptance.request
    put = fixtures.CoreAcceptance.put
    base = fixtures.CoreAcceptance.base
    review_extensions = fixtures.CoreAcceptance.review_extensions

    def stored(self):
        return list(self.core.db.iterdump())

    def test_startup_envelope_rejection_is_shared_private_and_atomic(self):
        state = self.path / 'startup-rejection'
        core = fixtures.Core(state)
        try:
            before = list(core.db.iterdump())
            envelope = {'goal': dict(fixtures.goal(), objective='private-goal-value'),
                'environment': {'secret': 'private-environment-value'},
                'resources': {'secret': 'private-resource-value'}}
            io = HostIO(state)
            with self.assertRaises(HostError) as caught:
                io.start(envelope)
            direct = subprocess.run([sys.executable, str(fixtures.SCRIPTS / 'synframe.py'),
                '--state', str(state), '--compact', 'solve', '--input', '-'],
                input=json.dumps(envelope), text=True, capture_output=True)
            self.assertEqual(caught.exception.returncode, 2)
            self.assertEqual(direct.returncode, 2)
            self.assertEqual(caught.exception.detail, json.loads(direct.stderr))
            detail = caught.exception.detail
            self.assertEqual(detail['path'], 'solve.input')
            self.assertEqual(detail['expected_type'], 'GoalSpec object')
            self.assertEqual(detail['unexpected_keys'], ['environment', 'goal', 'resources'])
            self.assertIn('JSON file path options', detail['guidance'])
            self.assertFalse(detail['applied'])
            self.assertIsNone(io.run_id)
            for value in ('private-goal-value', 'private-environment-value', 'private-resource-value'):
                self.assertNotIn(value, caught.exception.stdout + caught.exception.stderr
                    + direct.stdout + direct.stderr)
            self.assertEqual(before, list(core.db.iterdump()))
            for table in ('runs', 'entities', 'operations', 'events', 'checkpoints'):
                self.assertEqual(core.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
            with self.assertRaises(ContractError) as invalid:
                core.create(['private-nonobject-value'])
            self.assertEqual(invalid.exception.details['path'], 'solve.input')
            self.assertNotIn('private-nonobject-value', str(invalid.exception)
                + json.dumps(invalid.exception.details))
            self.assertEqual(before, list(core.db.iterdump()))
        finally:
            core.close()

    def test_raw_host_start_keeps_goal_and_initial_unassessed_responsibilities(self):
        io = HostIO(self.path / 'raw-startup')
        goal = fixtures.goal()
        original = copy.deepcopy(goal)
        run = io.start(goal)
        self.assertEqual(goal, original)
        self.assertEqual(run['state'], 'CREATED')
        self.assertEqual(io.run_id, run['id'])
        saved = io.call('get', id='goal')
        for field, value in goal.items():
            self.assertEqual(saved[field], value)
        self.assertEqual(run['environment'], {})
        self.assertEqual(run['resource_observations'], {'remaining_tokens': None, 'remaining_cost': None})
        tasks = {doc['id']: doc for doc in io.call('list') if doc['type'] == 'LearningTask'}
        self.assertEqual(set(tasks), {'goal:tool-scope', 'goal:goal-interpretation'})
        for task in tasks.values():
            self.assertEqual(task['answer']['status'], 'UNANSWERED')
            self.assertEqual(task['understanding']['status'], 'UNASSESSED')
            self.assertEqual(task['work_state'], 'READY')
            self.assertEqual(task['disposition'], 'OPEN')
        with self.assertRaisesRegex(ValueError, 'already has a run'):
            io.start(goal)

    def test_raw_solve_cli_preserves_explicit_environment_resource_files(self):
        state = self.path / 'explicit-startup'
        goal = fixtures.goal()
        environment = {'fixture': '명시 < & >', 'enabled': False}
        resources = {'remaining_tokens': None, 'remaining_cost': None,
            'explicit_zero': 0, 'explicit_false': False, 'ordered': ['later', 'first']}
        files = {}
        for name, value in [('goal', goal), ('environment', environment), ('resources', resources)]:
            path = self.path / (name + '-startup.json')
            path.write_text(json.dumps(value, ensure_ascii=False))
            files[name] = path
        result = subprocess.run([sys.executable, str(fixtures.SCRIPTS / 'synframe.py'),
            '--state', str(state), '--compact', 'solve', '--input', str(files['goal']),
            '--environment', str(files['environment']), '--resources', str(files['resources']),
            '--parent-run', self.run_id], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(result.stdout)
        self.assertEqual(run['state'], 'CREATED')
        self.assertEqual(run['environment'], environment)
        self.assertEqual(run['resource_observations'], resources)
        self.assertEqual(run['extensions']['parent_run_id'], self.run_id)
        io = HostIO(state, run['id'])
        self.assertEqual(io.call('status')['pending_operations'], [])
        saved = io.call('get', id='goal')
        for field, value in goal.items():
            self.assertEqual(saved[field], value)

        sibling_state = self.path / 'explicit-host-call-startup'
        unbound = HostIO(sibling_state)
        returned = unbound.call('solve', payload=goal, environment=files['environment'],
            resources=files['resources'], parent_run=self.run_id)
        self.assertIsNone(unbound.run_id)
        self.assertEqual(returned['state'], 'CREATED')
        self.assertEqual(returned['environment'], environment)
        self.assertEqual(returned['resource_observations'], resources)
        self.assertEqual(returned['extensions']['parent_run_id'], self.run_id)
        bound = HostIO(sibling_state, returned['id'])
        self.assertEqual(bound.call('status')['run']['id'], returned['id'])
        saved = bound.call('get', id='goal')
        for field, value in goal.items():
            self.assertEqual(saved[field], value)

    def test_entity_contract_exposes_actual_enums_and_nested_types(self):
        io = HostIO(self.path, self.run_id)
        contract = io.call('schema', entity='EvidenceRecord')
        self.assertIn('measured', contract['enums']['EvidenceRecord.observation_kind'])
        self.assertNotIn('direct_observation', contract['enums']['EvidenceRecord.observation_kind'])
        self.assertEqual(schema_catalog('GoalSpec')['structures']['GoalSpec.success_criteria[]'],
                         {'id': 'str', 'description': 'str'})
        self.assertEqual(schema_catalog('LearningTask')['structures']['LearningTask.answer.claims[]']['conditions'], 'list')
        self.assertNotIn('checks', contract)

    def test_edit_preserves_nested_original_and_does_not_repair_judgments(self):
        original = self.core.get(self.run_id, 'goal:goal-interpretation')
        saved = copy.deepcopy(original)
        edited = HostIO.edit(original)
        edited['assessment']['role'] = 'INDEPENDENT'
        edited['extensions']['interpretation_review']['handling'] = 'UNRESOLVED'
        self.assertEqual(original, saved)
        self.assertNotIn('revision', edited)
        self.assertEqual(edited['assessment']['role'], 'INDEPENDENT')
        self.assertEqual(edited['extensions']['interpretation_review']['handling'], 'UNRESOLVED')

    def test_patch_refs_predicts_explicit_new_versions_without_state_writes(self):
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request())
        changes = [evidence(claim='Changed synthetic observation'), evidence('new')]
        before = self.stored()
        predicted = self.core.patch_refs(self.run_id, changes)
        self.assertEqual(before, self.stored())
        self.assertEqual(predicted['refs'], {'ev': r('ev', 2), 'new': r('new')})
        result = output(op, changes, core=self.core)
        result['result_refs'] = list(predicted['refs'].values())
        self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        for identity, pointer in predicted['refs'].items():
            self.assertEqual(HostIO.reference(self.core.get(self.run_id, identity)), pointer)

    def test_patch_refs_rejects_reserved_type_metadata_and_duplicates(self):
        for changes in [[{'id': 'run', 'type': 'ReasoningRun'}],
                        [dict(evidence(), revision=1)], [evidence(), evidence()]]:
            with self.assertRaises(ContractError):
                self.core.patch_refs(self.run_id, changes)

    def test_preflight_runs_actual_apply_then_rolls_back_all_history(self):
        op = self.core.begin(self.run_id, self.request())
        raw = output(op, [evidence()], core=self.core)
        original = copy.deepcopy(raw)
        before = self.stored()
        checked = self.core.preflight(self.run_id, op['id'], raw)
        self.assertTrue(checked['validated'])
        self.assertFalse(checked['applied'])
        self.assertFalse(checked['predicted']['applied'])
        self.assertEqual(before, self.stored())
        self.assertEqual(raw, original)
        self.assertFalse(self.core.get(self.run_id, op['id'])['applied'])
        self.core.apply(self.run_id, op['id'], checked['prepared_result'])
        self.assertTrue(self.core.get(self.run_id, op['id'])['applied'])
        self.assertEqual(self.core.restore(self.run_id)['status']['run']['revision'], self.revision())

    def test_preflight_failure_preserves_pending_observation_and_all_state(self):
        op = self.core.begin(self.run_id, self.request())
        raw_path = self.path / 'raw.txt'
        raw_path.write_text('Synthetic raw observation, not a judgment')
        import hashlib
        self.core.record_observation(self.run_id, op['id'], self.revision(),
            [{'path': str(raw_path), 'sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(), 'source': 'fixture'}])
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'invalid observation kind'):
            self.core.preflight(self.run_id, op['id'], output(op, [evidence(observation_kind='direct_observation')]))
        self.assertEqual(before, self.stored())
        restored = self.core.restore(self.run_id)
        self.assertFalse(restored['status']['pending_operations'][0]['applied'])
        self.assertEqual(raw_path.read_text(), 'Synthetic raw observation, not a judgment')

    def test_preflight_never_refreshes_stale_reference(self):
        self.put([evidence()])
        prior_ref = r('ev')
        prior = self.core.get(self.run_id, 'ev')
        self.put([evidence(claim='Observed replacement for a saved old reference')])
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'stale reference') as direct:
            self.core.resolve(self.run_id, prior_ref)
        with self.core._read_view(self.run_id) as (_, resolve):
            with self.assertRaisesRegex(ContractError, 'stale reference') as snapshot:
                resolve(prior_ref)
        expected = {'requested_ref':r('ev'), 'current_ref':r('ev', 2),
                    'current_validity_status':'VALID'}
        self.assertEqual(direct.exception.details, expected)
        self.assertEqual(snapshot.exception.details, expected)
        self.assertEqual(prior_ref, r('ev'))
        self.assertEqual(self.core.resolve(self.run_id, prior_ref, valid=False), prior)
        self.assertEqual(before, self.stored())
        self.put([evidence('stale-origin'),
                  evidence('stale-consumer', provenance=[r('stale-origin')])])
        self.put([evidence('stale-origin', claim='Observed provider change')])
        invalidated = self.core.get(self.run_id, 'stale-consumer')
        self.assertEqual(invalidated['validity_status'], 'STALE')
        current_ref = HostIO.reference(invalidated)
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'stale reference') as direct:
            self.core.resolve(self.run_id, current_ref)
        with self.core._read_view(self.run_id) as (_, resolve):
            with self.assertRaisesRegex(ContractError, 'stale reference') as snapshot:
                resolve(current_ref)
        self.assertEqual(direct.exception.details, snapshot.exception.details)
        self.assertEqual(snapshot.exception.details, {'requested_ref':current_ref,
            'current_ref':current_ref, 'current_validity_status':'STALE'})
        self.assertEqual(before, self.stored())
        op = self.core.begin(self.run_id, self.request())
        changed = evidence(claim='Synthetic changed evidence')
        stale = evidence('consumer', provenance=[r('ev', 2)])
        raw = output(op, [changed, stale])
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'wrong new revision'):
            self.core.preflight(self.run_id, op['id'], raw)
        self.assertEqual(stale['provenance'], [r('ev', 2)])
        self.assertEqual(before, self.stored())
        raw['proposed_state_changes'][1]['provenance'] = [
            self.core.patch_refs(self.run_id, [changed])['refs']['ev']]
        checked = self.core.preflight(self.run_id, op['id'], raw)
        self.core.apply(self.run_id, op['id'], checked['prepared_result'])

    def test_preflight_does_not_reserve_or_auto_rebase_later_apply(self):
        op = self.core.begin(self.run_id, self.request())
        checked = self.core.preflight(self.run_id, op['id'], output(op, [evidence()]))
        self.core.begin(self.run_id, self.request('SIMPLIFY'))
        with self.assertRaisesRegex(ContractError, 'revision conflict'):
            self.core.apply(self.run_id, op['id'], checked['prepared_result'])

    def test_preflight_keeps_current_comparison_observation_binding_required(self):
        op = self.core.begin(self.run_id, self.request())
        closed = HostIO.edit(self.core.get(self.run_id, 'goal:goal-interpretation'))
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'preserved actual comparison binding'):
            self.core.preflight(self.run_id, op['id'], output(op, [closed]))
        self.assertEqual(before, self.stored())

    def test_review_context_uses_canonical_question_projection_after_asset_filter(self):
        self.base()
        self.put([task(), asset('unused', understanding=[{'context': 'fixture', 'level': 1,
            'questions': [r('task')], 'evidence_refs': [r('ev')], 'stop_condition': 'fixture'}])])
        before = self.stored()
        context = self.core.review_context(self.run_id, r('candidate'))
        keys = {q['key'] for q in context['information_needs']}
        self.assertIn('task', keys)
        self.assertFalse(any(key.startswith('unused/') for key in keys))
        extensions = self.review_extensions()
        self.assertEqual(keys, set(extensions['question_assessments']))
        self.assertEqual(context['information_need_refs'], sorted(extensions['information_need_refs'], key=lambda p: p['id']))
        self.assertNotIn('checks', context)
        self.assertEqual(before, self.stored())

    def test_review_context_exposes_existing_gate_subject_defects_before_authorship(self):
        # Reproduce the observed shape: every derived capability is proved, but
        # one source criterion has no capability and a selected asset has no
        # contextual assessment. Neither graph coverage nor I/O catches these.
        goal = fixtures.goal()
        goal['success_criteria'].append({'id':'method', 'description':'A grounded method is required'})
        goal['extensions']['goal_alignment']['facets'][0]['criterion_ids'].append('method')
        self.run = self.core.create(goal)
        self.run_id = self.run['id']
        self.core.transition(self.run_id, 'ACTIVE', 1, 'Begin declared subject-readiness fixture')
        fixtures.settle_interpretation_fixture(self)
        self.put(fixtures.declared_scope_fixture(self.core.get(self.run_id, 'goal:tool-scope')))
        self.put([evidence(), fixtures.capability(), asset(understanding=[]),
                  fixtures.link(), fixtures.candidate()])
        before = self.stored()
        context = self.core.review_context(self.run_id, r('candidate'))
        self.assertEqual(before, self.stored())
        self.assertEqual(context['structure']['coverage']['missing'], [])
        self.assertEqual(context['structure']['io_errors'], [])
        expected = ['goal success criteria lack capability derivation',
                    'no contextual understanding assessment: asset']
        self.assertEqual(context['structure']['errors'], expected)
        self.assertNotIn('checks', context)
        self.assertNotIn('passed', context)
        review_ref = fixtures.CoreAcceptance.review(self)
        gate = self.core.commit_gate(self.run_id, r('candidate'), review_ref)
        self.assertFalse(gate['passed'])
        self.assertEqual(gate['errors'], expected)

    def test_review_selection_context_preserves_declared_values_and_unknown_evidence_readonly(self):
        self.base()
        self.put([evidence('indirect'), evidence('unused-evidence'),
            evidence('unknown', claim='Unconfirmed condition: \"조건\" <量> & next\nline',
                observation_kind='unknown', verification_status='UNVERIFIED',
                provenance=[r('indirect')]),
            {**asset('selected-b', availability='unknown', understanding=[],
                provenance=[r('unknown')]), 'identity':'도구 B / 条件'},
            asset('unused', understanding=[], provenance=[r('unused-evidence')]),
            fixtures.candidate(asset_refs=[r('selected-b'), r('asset')],
                attributes={'cost':None, 'order':['later', 'first'], 'condition':'미확인 < & >'},
                comparison_rationale='Declared comparison only.\n추가 부담은 미확인.',
                provenance=[r('unknown')])])
        before = self.stored()
        context = self.core.review_context(self.run_id, r('candidate', 2))
        selection = context['selection_context']
        self.assertEqual(selection['candidate'], self.core.get(self.run_id, 'candidate'))
        self.assertEqual(selection['selected_assets'], [self.core.get(self.run_id, identity)
            for identity in ('selected-b', 'asset')])
        records = {record['id']:record for record in selection['evidence']}
        self.assertEqual(set(records), {'unknown', 'ev'})
        self.assertEqual(records['unknown'], self.core.get(self.run_id, 'unknown'))
        self.assertEqual(records['unknown']['verification_status'], 'UNVERIFIED')
        self.assertEqual(records['unknown']['observation_kind'], 'unknown')
        self.assertFalse({'checks', 'passed', 'recommendation', 'score'} & set(selection))
        self.assertEqual(before, self.stored())

    def test_review_selection_context_rejects_old_candidate_without_refresh_or_cache(self):
        self.base()
        previous = self.core.review_context(self.run_id, r('candidate'))
        original = copy.deepcopy(previous)
        self.put([HostIO.edit(previous['selection_context']['candidate'],
            comparison_rationale='A newly declared comparison; no automatic approval')])
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'stale reference'):
            self.core.review_context(self.run_id, r('candidate'))
        current = self.core.review_context(self.run_id, r('candidate', 2))
        self.assertEqual(current['selection_context']['candidate'],
                         self.core.get(self.run_id, 'candidate'))
        self.assertNotEqual(current['selection_context']['candidate']['comparison_rationale'],
                            previous['selection_context']['candidate']['comparison_rationale'])
        self.assertEqual(previous, original)
        self.assertEqual(before, self.stored())

    def test_empty_subject_errors_do_not_approve_host_review_checks(self):
        self.base()
        before = self.stored()
        context = self.core.review_context(self.run_id, r('candidate'))
        self.assertEqual(context['structure']['errors'], [])
        self.assertEqual(before, self.stored())
        review_ref = fixtures.CoreAcceptance.review(self, changes={'coverage':{
            'status':'UNKNOWN', 'rationale':'Declared host condition is still unverified',
            'evidence_refs':[r('ev')]}})
        gate = self.core.commit_gate(self.run_id, r('candidate'), review_ref)
        self.assertFalse(gate['passed'])
        self.assertIn('missing/failed/ungrounded semantic check: coverage', gate['errors'])

    def test_host_error_preserves_machine_diagnostics_and_original_output(self):
        io = HostIO(self.path, self.run_id)
        op = self.core.begin(self.run_id, self.request())
        with self.assertRaises(HostError) as caught:
            io.preflight(op, output(op, [evidence(observation_kind='direct_observation')]))
        self.assertEqual(caught.exception.returncode, 2)
        self.assertIn('ev (EvidenceRecord): invalid observation kind', caught.exception.detail['message'])
        self.assertFalse(caught.exception.detail['applied'])
        self.assertTrue(caught.exception.stderr)
        self.assertFalse(self.core.get(self.run_id, op['id'])['applied'])

    def test_preserve_files_returns_exact_raw_binding_without_evidence_or_answers(self):
        io = HostIO(self.path, self.run_id)
        op = self.core.begin(self.run_id, self.request())
        raw = self.path / 'receipt.txt'
        raw.write_text('Actual synthetic bytes')
        before = self.core.get(self.run_id, 'goal:goal-interpretation')
        saved = io.preserve_files(op, [(raw, 'fixture source')], expected_revision=self.revision())
        receipt = saved['extensions']['actual_observations'][0]
        self.assertEqual(receipt['path'], str(raw.resolve()))
        self.assertEqual(receipt['source'], 'fixture source')
        self.assertEqual(before, self.core.get(self.run_id, 'goal:goal-interpretation'))
        self.assertFalse(any(d['id'] == 'receipt-evidence' for d in self.core.documents(self.run_id)))
        self.assertFalse(saved['applied'])

    def test_installed_style_cli_read_only_helpers_and_preflight(self):
        io = HostIO(self.path, self.run_id)
        self.base()
        self.assertEqual(io.review_context(r('candidate'))['candidate_ref'], r('candidate'))
        op = self.core.begin(self.run_id, self.request())
        changes = [evidence('added')]
        self.assertEqual(io.patch_refs(changes)['refs']['added'], r('added'))
        checked = io.preflight(op, output(op, changes))
        self.assertFalse(checked['applied'])
        io.finish(op, checked['prepared_result'])
        self.assertEqual(io.call('get', id='added')['revision'], 1)

    def test_authoring_schema_exposes_rejected_shapes_without_defaults(self):
        from synframe_core.learning import DISCOVERY_FIELDS, JUDGMENT_FIELDS, validate_shape
        contract = schema_catalog('LearningTask')
        self.assertEqual(set(contract['structures']['LearningTask.expansion.discoveries[]']), DISCOVERY_FIELDS)
        self.assertEqual(set(contract['learning_plan']['judgment_target']), JUDGMENT_FIELDS)
        self.assertEqual(contract['structures']['LearningTask.extensions.interpretation_review']['assumptions'], 'nonempty str')
        self.assertEqual(contract['structures']['LearningTask.extensions.interpretation_review.interpretations[]']['uncertainties'], 'nonempty str')
        self.assertIn('mechanism', schema_catalog('Frame')['enums']['Frame.transformation'])
        self.assertEqual(schema_catalog('ReviewRecord')['structures']['ReviewRecord.extensions.independent_followups'],
                         'dict keyed by current task ID, not list')
        sample = task()
        sample['expansion']['discoveries'] = [{**dict.fromkeys(DISCOVERY_FIELDS, 'fixture observation'),
            'assessment': 'UNKNOWN', 'disposition': None, 'target_refs': [], 'observation_kind': 'measured'}]
        validate_shape(sample)
        del sample['expansion']['discoveries'][0]['understanding_gap']
        with self.assertRaisesRegex(ContractError, 'invalid discovery item'):
            validate_shape(sample)

    def build(self, io, op, changes):
        return io.build_result(op, changes, result_ids=[d['id'] for d in changes], preserved_refs=[],
            evidence_refs=[], unresolved_items=['Goal obligations remain unassessed'],
            observed_effects=['Declared authoring fixture'], next_decision_inputs=['Inspect actual stored state'],
            outcome='SUCCEEDED', learning_results=[], propagation_resolutions=[], path_assessments=[])

    def test_explicit_patch_markers_bind_new_versions_and_preserve_literal_history(self):
        io = HostIO(self.path, self.run_id)
        self.put([evidence()])
        op = self.core.begin(self.run_id, self.request())
        changes = [evidence(claim='Changed declared observation'),
                   evidence('consumer', provenance=[io.patch_ref('ev')],
                       extensions={'original_observation_ref': r('goal')})]
        original = copy.deepcopy(changes);before = self.stored()
        interpretation = self.core.get(self.run_id, 'goal:goal-interpretation')
        result = self.build(io, op, changes)
        self.assertEqual(result['proposed_state_changes'][1]['provenance'], [r('ev', 2)])
        self.assertEqual(result['proposed_state_changes'][1]['extensions']['original_observation_ref'], r('goal'))
        self.assertEqual(changes, original);self.assertEqual(before, self.stored())
        io.finish(op, result)
        self.assertEqual(self.core.get(self.run_id, 'consumer')['provenance'], [r('ev', 2)])
        self.assertNotIn('$patch_ref', str(self.core.documents(self.run_id)))
        self.assertEqual(self.core.get(self.run_id, 'goal:goal-interpretation'), interpretation)

    def test_marker_errors_do_not_write_and_literal_stale_refs_still_fail(self):
        io = HostIO(self.path, self.run_id);self.put([evidence()])
        op = self.core.begin(self.run_id, self.request());before = self.stored()
        for marker in [io.patch_ref('absent'), {'$patch_ref': 'ev', 'revision': 2}, {'$patch_ref': []}]:
            with self.assertRaises(ValueError):
                self.build(io, op, [evidence(), evidence('consumer', provenance=[marker])])
            self.assertEqual(before, self.stored())
        result = self.build(io, op, [evidence(claim='changed'), evidence('consumer', provenance=[r('ev')])])
        with self.assertRaisesRegex(HostError, 'wrong new revision'):
            io.finish(op, result)
        self.assertEqual(before, self.stored())

    def test_explicit_declared_ports_bind_and_apply_without_inferred_adapter(self):
        from synframe_core.graph import check_io
        io = HostIO(self.path, self.run_id)
        self.put([evidence(), fixtures.capability(), asset('source', understanding=[], outputs=[{'name':'tokens','type':'record'}]),
                  asset('target', understanding=[], inputs=[{'name':'theme','type':'record'}])])
        source = io.edit(self.core.get(self.run_id, 'source'), version='fixture-v2')
        target = self.core.get(self.run_id, 'target')
        connection = io.connect(source, 'tokens', target, 'theme', evidence_refs=[r('ev')])
        op = self.core.begin(self.run_id, self.request())
        candidate = fixtures.candidate(asset_refs=[io.patch_ref('source'), r('target')],
            connections=[connection])
        proof = fixtures.link(sources=[io.patch_ref('source')])
        io.finish(op, self.build(io, op, [source, proof, candidate]))
        saved = self.core.get(self.run_id, 'candidate')
        self.assertEqual(saved['connections'][0]['from_ref'], r('source', 2))
        self.assertEqual(saved['connections'][0]['to_ref'], r('target'))
        self.assertEqual(check_io(saved, lambda p:self.core.resolve(self.run_id,p)), [])

    def test_port_authoring_errors_leave_state_and_evidence_unapproved(self):
        source = asset('source', understanding=[], outputs=[{'name':'data','type':'record'}])
        target = asset('target', understanding=[], inputs=[{'name':'data','type':'text'}])
        before = self.stored()
        for output_name, input_name in [('description', 'data'), ('data', 'data')]:
            with self.assertRaises(ValueError):
                HostIO.connect(source, output_name, target, input_name, evidence_refs=[r('ev')])
        target['inputs'][0]['type'] = 'record'
        binding = HostIO.connect(source, 'data', target, 'data', evidence_refs=[r('unknown-evidence')])
        self.assertEqual(binding['evidence_refs'], [r('unknown-evidence')])
        self.assertEqual(before, self.stored())

    def test_host_artifact_path_uses_positional_cli_and_real_bytes(self):
        import hashlib
        path = self.path/'actual output.txt';path.write_text('Actual local bytes')
        before = self.stored()
        result = HostIO(self.path, self.run_id).call('artifact', path=path, source='Declared fixture source')
        self.assertEqual(result, {'path':str(path.resolve()), 'source':'Declared fixture source',
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        self.assertEqual(before, self.stored())

    def test_observation_uses_expected_run_revision_and_never_rebases_stale_operation(self):
        io = HostIO(self.path, self.run_id)
        op = self.core.begin(self.run_id, self.request())
        self.assertNotEqual(op['revision'], op['extensions']['expected_apply_revision'])
        raw = self.path/'observed.txt'; raw.write_text('Declared fixture bytes')
        updated = io.preserve_files(op, [(raw, 'fixture')])
        before = self.stored()
        with self.assertRaisesRegex(HostError, 'revision conflict'):
            io.preserve_files(op, [(raw, 'fixture')])
        self.assertEqual(before, self.stored())
        self.assertEqual(io.preserve_files(updated, [(raw, 'fixture')]), updated)
        self.assertEqual(before, self.stored())

    def test_draft_checks_package_and_learning_answer_shapes_before_writing(self):
        io = HostIO(self.path, self.run_id)
        op = self.core.begin(self.run_id, self.request()); before = self.stored()
        package = {'id':'package', 'type':'SolutionPackage', 'candidate_ref':r('candidate'),
            'review_ref':r('review'), 'contents':{'goal':'Wrong field name'}, 'completion_scope':'fixture',
            'artifact_refs':[], 'validation_refs':[], 'uncertainties':[]}
        with self.assertRaisesRegex(ContractError, 'all ten output fields'):
            self.build(io, op, [package])
        result = self.build(io, op, [evidence()])
        result['learning_results'] = [{'task_ref':r('task'), 'result_ref':r('task',2),
            'answer_refs':[{'owner_ref':r('task',2), 'item_id':'answer'}],
            'understanding_change':'fixture', 'discovery_ids':[], 'upward_effects':['fixture'],
            'observations':['fixture'], 'prediction_difference':'fixture'}]
        with self.assertRaisesRegex(ContractError, 'exactly id and revision'):
            io.finish(op, result)
        self.assertEqual(before, self.stored())
        from synframe_core.schema import PACKAGE_FIELDS
        self.assertEqual(set(schema_catalog('SolutionPackage')['structures']['SolutionPackage.contents']), PACKAGE_FIELDS)
        self.assertIn('EvidenceRecord', schema_catalog('OperationRecord')['structures'][
            'OperationRecord.result.learning_results[]']['answer_refs'])

    def test_late_marker_is_rejected_locally_without_automatic_reference_or_closure_repair(self):
        from unittest.mock import patch
        io = HostIO(self.path, self.run_id); op = self.core.begin(self.run_id, self.request())
        result = self.build(io, op, [evidence()]); before = self.stored()
        result['proposed_state_changes'][0]['provenance'] = [io.patch_ref('ev')]
        with patch.object(io, 'call', wraps=io.call) as calls:
            with self.assertRaisesRegex(ContractError, r'proposed_state_changes\[0\].provenance\[0\].*build_result again'):
                io.finish(op, result)
            calls.assert_not_called()
        self.assertEqual(before, self.stored())
        self.assertEqual(result['proposed_state_changes'][0]['provenance'], [io.patch_ref('ev')])

    def test_copied_derived_proof_is_recomputed_but_authored_stale_dependencies_still_fail(self):
        self.base(); io = HostIO(self.path, self.run_id)
        original = self.core.get(self.run_id, 'candidate'); old_asset = self.core.get(self.run_id, 'asset')
        asset_patch = io.edit(old_asset, version='fixture-v2')
        edge_patch = io.edit(self.core.get(self.run_id, 'link'), sources=[r('asset',2)])
        chosen = io.edit(original, asset_refs=[r('asset',2)])
        op = self.core.begin(self.run_id, self.request())
        changes = [asset_patch, edge_patch, chosen]
        raw = output(op, changes, core=self.core)
        bad = copy.deepcopy(raw)
        bad['proposed_state_changes'][-1]['extensions']['judgment_dependencies'] = [
            {'source_ref':r('asset'), 'role':'COMPARES_USING', 'required':True,
             'scope':'fixture selection', 'rationale':'Explicit host ground must remain checked'}]
        before = self.stored()
        with self.assertRaisesRegex(ContractError, 'wrong new revision'):
            self.core.preflight(self.run_id, op['id'], bad)
        self.assertEqual(before, self.stored())
        checked = self.core.preflight(self.run_id, op['id'], raw)
        self.assertEqual(before, self.stored())
        io.finish(op, checked['prepared_result'])
        saved = self.core.get(self.run_id, 'candidate')
        self.assertIn(r('asset',2), saved['extensions']['functional_proof_refs'])
        self.assertNotIn(r('asset'), saved['extensions']['functional_proof_refs'])
        self.assertEqual(self.core.get(self.run_id, 'candidate', original['revision']), original)

    def test_finish_uses_one_cli_call_and_preserves_retry_and_revision_guards(self):
        from unittest.mock import patch
        io = HostIO(self.path, self.run_id); op = self.core.begin(self.run_id, self.request())
        result = self.build(io, op, [evidence()])
        with patch.object(io, 'call', wraps=io.call) as calls:
            self.assertTrue(io.finish(op, result)['applied'])
            self.assertEqual([c.args[0] for c in calls.call_args_list], ['finish'])
        before = self.stored()
        self.assertTrue(io.finish(op, result)['duplicate']); self.assertEqual(before, self.stored())
        op = self.core.begin(self.run_id, self.request()); result = self.build(io, op, [evidence('later')])
        self.core.begin(self.run_id, self.request('SIMPLIFY')); before = self.stored()
        with self.assertRaisesRegex(HostError, 'revision conflict'):
            io.finish(op, result)
        self.assertEqual(before, self.stored())


if __name__ == '__main__':
    unittest.main()
