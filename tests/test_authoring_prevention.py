"""Mechanical authoring regressions; declared fixtures are not autonomous evidence."""
import copy
import unittest

import test_core as f
from test_learning import task, dep
import test_interpretation_rebinding as rb
from synframe_core.schema import ContractError, same_references, validate_decision
from synframe_host import HostIO


class AuthoringPrevention(unittest.TestCase):
    setUp = f.CoreAcceptance.setUp
    tearDown = f.CoreAcceptance.tearDown
    request = f.CoreAcceptance.request
    put = f.CoreAcceptance.put
    revision = f.CoreAcceptance.revision
    base = f.CoreAcceptance.base
    review_extensions = f.CoreAcceptance.review_extensions
    review = f.CoreAcceptance.review

    def test_work_context_accepts_explicit_operation_id_without_inventing_or_rebasing_it(self):
        op = self.core.begin(self.run_id, self.request())
        io = HostIO(self.path, self.run_id)
        before = list(self.core.db.iterdump())
        self.assertEqual(io.work_context(op), io.work_context(op['id']))
        for invalid in ('', 1, [], {}, {'id':1}):
            with self.assertRaisesRegex(ValueError, 'operation ID'):
                io.work_context(invalid)
        self.assertEqual(before, list(self.core.db.iterdump()))

    def test_existing_contextual_k_gate_error_is_visible_before_authoring_review(self):
        a = f.asset(); a['understanding'][0]['questions'] = []
        self.put([f.evidence(), f.capability(), a, f.link(), f.candidate()])
        error = 'contextual K lacks decision/application question evidence: asset'
        context = self.core.review_context(self.run_id, f.r('candidate'))
        self.assertIn(error, context['structure']['errors'])
        review = self.review()
        gate = self.core.commit_gate(self.run_id, f.r('candidate'), review)
        self.assertFalse(gate['passed'])
        self.assertIn(error, gate['errors'])

    def test_identity_coverage_ignores_order_but_not_duplicates_versions_or_missing_items(self):
        self.assertTrue(same_references([f.r('b'), f.r('a')], [f.r('a'), f.r('b')]))
        for actual in ([f.r('a')], [f.r('a'), f.r('a')], [f.r('a'), f.r('b', 2)],
                       [f.r('a'), f.r('b'), f.r('c')]):
            self.assertFalse(same_references(actual, [f.r('a'), f.r('b')]))

    def test_reversed_learning_bundles_apply_and_wrong_versions_still_roll_back(self):
        self.put([f.evidence(), task('a'), task('b')])
        plans = []
        for identity in ('a', 'b'):
            plan = copy.deepcopy(f.interpretation_plan(self.core.get(self.run_id, 'goal:goal-interpretation'))['learning_plan'][0])
            plan.update(task_ref=f.r(identity), requirement_ids=['ability'])
            plan['judgment_target'].update(target_ref=f.r(identity), consumer_refs=[f.r(identity)])
            plans.append(plan)
        op = self.core.begin(self.run_id, self.request('DEEPEN_KNOWLEDGE', {
            'learning_task_refs':[f.r('a'), f.r('b')], 'learning_plan':list(reversed(plans))}))
        result = f.output(op, [task('a', True), task('b', True)], core=self.core)
        result['learning_results'] = [{'task_ref':f.r(i), 'result_ref':f.r(i, 2),
            'answer_refs':[f.r('ev')], 'understanding_change':'Declared fixture ability supported',
            'discovery_ids':[], 'upward_effects':['Declared fixture consumer comparison'],
            'observations':['Declared fixture observation'], 'prediction_difference':'Declared bounded result'}
            for i in ('b', 'a')]
        before = list(self.core.db.iterdump())
        wrong = copy.deepcopy(result); wrong['learning_results'][0]['task_ref']['revision'] = 99
        with self.assertRaisesRegex(ContractError, 'cover selected'):
            self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], wrong))
        self.assertEqual(before, list(self.core.db.iterdump()))
        self.assertTrue(self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))['applied'])

    def test_projection_exposes_successor_obligations_without_writing_or_assessing(self):
        consumer = task('consumer'); consumer['dependency_refs'] = [dep('provider')]
        self.put([f.evidence(), task('provider'), consumer])
        old = HostIO.edit(self.core.get(self.run_id, 'provider')); old['question'] += ' first change'
        self.put([old])
        old_obligation = next(o for o in self.core.status(self.run_id)['propagation_obligations']
            if o['source_ref']['id'] == 'provider' and o['status'] == 'PENDING')
        change = HostIO.edit(self.core.get(self.run_id, 'provider')); change['question'] += ' second change'
        before = list(self.core.db.iterdump())
        projection = self.core.patch_refs(self.run_id, [change])
        self.assertEqual(before, list(self.core.db.iterdump()))
        obligations = {o['id']:o for o in projection['propagation_obligations']}
        obsolete = obligations[old_obligation['id']]
        self.assertEqual(obsolete['status'], 'SUPERSEDED')
        successor = obligations[obsolete['superseded_by']]
        self.assertEqual(successor['source_ref'], f.r('provider', 3))
        self.assertEqual(successor['status'], 'PENDING')
        self.assertEqual(successor['remaining_work'], old_obligation['remaining_work'])
        self.assertIsNone(successor['assessment'])
        self.assertEqual(successor['result_refs'], [])
        with self.assertRaises(ContractError) as rejected:
            self.core._validate_resolutions(self.run_id, [{'id':obsolete['id'], 'assessment':'MAINTAIN',
                'rationale':'Fixture', 'evidence_refs':[f.r('ev')], 'result_refs':[f.r('consumer')],
                'remaining_work':[]}], [successor])
        self.assertEqual(rejected.exception.details['superseded_by'], successor['id'])

    def test_projection_reports_exact_literal_path_and_keeps_explicit_markers_distinct(self):
        self.base()
        change = HostIO.edit(self.core.get(self.run_id, 'asset'))
        change['identity'] = 'Explicit changed identity'
        ca = HostIO.edit(self.core.get(self.run_id, 'candidate'))
        before = list(self.core.db.iterdump())
        packet = self.core.patch_refs(self.run_id, [change, ca])
        conflict = next(c for c in packet['reference_conflicts'] if c['owner_ref']['id'] == 'candidate'
                        and c['path'] == ['asset_refs', 0])
        self.assertEqual(conflict['declared_ref'], f.r('asset'))
        self.assertEqual(conflict['current_ref'], f.r('asset', 2))
        self.assertEqual(ca['asset_refs'], [f.r('asset')])
        ca['asset_refs'] = [HostIO.patch_ref('asset')]
        packet = self.core.patch_refs(self.run_id, [change, ca])
        self.assertFalse(any(c['path'] == ['asset_refs', 0] and c['owner_ref']['id'] == 'candidate'
                             for c in packet['reference_conflicts']))
        self.assertEqual(before, list(self.core.db.iterdump()))

        self.assertIn('$patch_ref', ca['asset_refs'][0])
        # An earlier observation's version is a historical locator, not a
        # claim that the old version is the new patch's current dependency.
        observed = f.evidence('observed', environment={'subject':f.r('asset')})
        packet = self.core.patch_refs(self.run_id, [change, observed])
        self.assertTrue(any(c['owner_ref']['id'] == 'observed' and c['path'] == ['environment', 'subject']
                            for c in packet['reference_conflicts']))
        observed['environment']['subject'] = 'asset@1 (observed before the proposed update)'
        packet = self.core.patch_refs(self.run_id, [change, observed])
        self.assertFalse(any(c['owner_ref']['id'] == 'observed' for c in packet['reference_conflicts']))
        self.assertEqual(observed['environment']['subject'], 'asset@1 (observed before the proposed update)')
        self.assertEqual(before, list(self.core.db.iterdump()))

    def test_diagnostic_paths_do_not_confuse_identical_active_and_historical_values(self):
        self.put([f.evidence(), task('q')])
        q = self.core.get(self.run_id, 'q')
        # The same literal may occur in both locations; only the active path
        # should be diagnosed. An equality filter over all fields is unsound.
        q['origin_refs'] = [f.r('ev')]
        q['dependency_refs'] = [dep('ev')]
        ev = self.core.get(self.run_id, 'ev'); ev['revision'] = 2
        conflicts = self.core._reference_conflicts([q, ev])
        self.assertTrue(any(c['path'] == ['dependency_refs', 0, 'source_ref'] for c in conflicts))
        self.assertFalse(any(c['path'][0] == 'origin_refs' for c in conflicts))

    def test_projection_shows_transitive_consumers_and_matches_actual_invalidation(self):
        self.base()
        change = HostIO.edit(self.core.get(self.run_id, 'asset')); change['identity'] += ' changed'
        projection = self.core.patch_refs(self.run_id, [change])
        affected = {i['previous_ref']['id']:i for i in projection['invalidated_consumers']}
        self.assertIn('candidate', affected)
        op = self.core.begin(self.run_id, self.request('SIMPLIFY'))
        result = f.output(op, [change], core=self.core)
        actual = self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        self.assertEqual(set(actual['invalidated']), set(affected))
        for identity, item in affected.items():
            saved = self.core.get(self.run_id, identity)
            self.assertEqual(HostIO.reference(saved), item['projected_ref'])
            self.assertEqual(saved['validity_status'], item['projected_validity_status'])

    def test_available_action_codes_are_explicit_and_not_repaired_from_labels(self):
        judgment = self.request('SIMPLIFY')['decision']
        judgment['ddc']['available_actions'] = ['SIMPLIFY interpretation_rebind', 'DEEPEN_KNOWLEDGE']
        original = copy.deepcopy(judgment)
        with self.assertRaises(ContractError) as rejected:
            validate_decision(judgment)
        self.assertEqual(rejected.exception.details['path'], 'ddc.available_actions')
        self.assertEqual(judgment, original)
        judgment['ddc']['available_actions'] = ['SIMPLIFY', 'DEEPEN_KNOWLEDGE']
        validate_decision(judgment)


class ReviewRepairContext(unittest.TestCase):
    setUp = rb.InterpretationRebindingAcceptance.setUp
    tearDown = rb.InterpretationRebindingAcceptance.tearDown
    revision = rb.InterpretationRebindingAcceptance.revision
    request = rb.InterpretationRebindingAcceptance.request
    put = rb.InterpretationRebindingAcceptance.put
    base = rb.InterpretationRebindingAcceptance.base
    task = rb.InterpretationRebindingAcceptance.task
    errors = rb.InterpretationRebindingAcceptance.errors
    finish = rb.InterpretationRebindingAcceptance.finish
    closed_consumer = rb.InterpretationRebindingAcceptance.closed_consumer
    settle_interpretation_fixture = False

    def test_broken_nested_binding_keeps_repair_inputs_visible_without_a_fake_snapshot(self):
        self.closed_consumer()
        ca = HostIO.edit(self.core.get(self.run_id, 'candidate'))
        ca.setdefault('extensions', {})['judgment_dependencies'] = [{
            'source_ref':HostIO.reference(self.task()), 'role':'USES_PROOF', 'required':True,
            'scope':'Fixture interpretation selection', 'rationale':'Explicit fixture dependence'}]
        self.put([ca], 'SIMPLIFY')
        before = list(self.core.db.iterdump())
        packet = self.core.review_context(self.run_id, f.r('candidate', 3))
        self.assertIsNone(packet['snapshot'])
        self.assertTrue(packet['reference_errors'])
        self.assertTrue(any(c['declared_ref'] == f.r('candidate') and c['current_ref'] == f.r('candidate', 3)
                            for c in packet['reference_conflicts']))
        self.assertTrue(packet['requirements_context']['learning_tasks'])
        self.assertEqual(before, list(self.core.db.iterdump()))
        with self.assertRaises(ContractError):
            self.core.snapshot(self.run_id, f.r('candidate', 3))
        # Even diagnostics refuse a stale top-level requested candidate.
        with self.assertRaises(ContractError):
            self.core.review_context(self.run_id, f.r('candidate'))

    def test_rebind_projection_exposes_consumers_that_need_explicit_atomic_changes(self):
        self.closed_consumer()
        ca = self.core.get(self.run_id, 'candidate')
        ca_patch = HostIO.edit(ca)
        ca_patch.setdefault('extensions', {})['judgment_dependencies'] = [{
            'source_ref':HostIO.reference(self.task()), 'role':'USES_PROOF', 'required':True,
            'scope':'Fixture interpretation selection', 'rationale':'Explicit fixture dependence'}]
        self.put([ca_patch], 'SIMPLIFY')
        patch = HostIO.edit(self.task())
        patch['closure_assessment']['rationale'] += ' explicit consumer comparison'
        packet = self.core.patch_refs(self.run_id, [patch])
        self.assertTrue(any(c['previous_ref']['id'] == 'candidate' for c in packet['invalidated_consumers']))


if __name__ == '__main__':
    unittest.main()
