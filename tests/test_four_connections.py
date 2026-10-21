"""Scoped structural/negative controls, never autonomous concept discovery."""
import copy
import hashlib
import unittest
from pathlib import Path
from unittest import mock

import test_core as f
from test_learning import task
from synframe_core.files import validate_artifacts
from synframe_host import HostIO


class FourConnectionAcceptance(unittest.TestCase):
    setUp = f.CoreAcceptance.setUp
    tearDown = f.CoreAcceptance.tearDown
    revision = f.CoreAcceptance.revision
    request = f.CoreAcceptance.request
    put = f.CoreAcceptance.put
    base = f.CoreAcceptance.base
    review = f.CoreAcceptance.review
    review_extensions = f.CoreAcceptance.review_extensions
    commit = f.CoreAcceptance.commit
    package = f.CoreAcceptance.package
    completion = f.CoreAcceptance.completion

    def gate(self, revision=1):
        return self.core.commit_gate(self.run_id, f.r('candidate'), f.r('review', revision))

    def revise_review(self, change):
        self.review()
        review = HostIO.edit(self.core.get(self.run_id, 'review'))
        change(review['extensions']['capability_conditions']['cap'])
        self.put([review], 'REVIEW_SOLUTION')
        return self.gate(2)

    def learning_result(self, extra=(), outcome='SUCCEEDED'):
        saved = self.core.get(self.run_id, 'quality')
        plan = f.interpretation_plan(saved)
        plan['learning_plan'][0]['judgment_target'].update(
            target_ref=f.r('cap'), consumer_refs=[f.r('cap')])
        op = self.core.begin(self.run_id, self.request('DEEPEN_KNOWLEDGE', plan))
        result = f.output(op, [task('quality', True), *extra], core=self.core, outcome=outcome)
        result['learning_results'] = [{'task_ref': f.r('quality'), 'result_ref': f.r('quality', 2),
            'answer_refs': [f.r('ev')], 'understanding_change': 'Declared observed fixture condition',
            'discovery_ids': [], 'upward_effects': ['Reassess the exact cap condition'],
            'observations': ['Synthetic observation inspected'],
            'prediction_difference': 'Explicit fixture, not autonomous understanding'}]
        return op, result

    def quality_setup(self, relation=None):
        cap = f.capability()
        cap['extensions']['questions'] = [f.r('quality')]
        changes = [f.evidence(), task('quality'), cap]
        if relation:
            changes.append(f.link('quality-effect', [f.r('quality')], 'cap', relation))
        self.put(changes)

    def test_criterion_coverage_without_scoped_ability_basis_cannot_be_adopted(self):
        self.base()
        self.assertFalse(self.core.work_context(self.run_id)['requirements_context']['missing_capability_criterion_ids'])
        gate = self.revise_review(lambda check: check.pop('understanding_basis'))
        self.assertFalse(gate['passed'])
        self.assertIn('understanding_basis', ' '.join(gate['errors']))

    def test_direct_grounded_reuse_needs_no_new_domain_task_or_search(self):
        self.base()
        before = {d['id'] for d in self.core.documents(self.run_id) if d['type'] == 'LearningTask'}
        self.review()
        self.assertTrue(self.gate()['passed'])
        self.assertEqual(before, {d['id'] for d in self.core.documents(self.run_id) if d['type'] == 'LearningTask'})
        self.assertEqual(self.core.get(self.run_id, 'review')['extensions']['capability_conditions']['cap']
            ['understanding_basis'][0]['task_requirements'], [])

    def test_wrong_criterion_and_unknown_required_ability_are_rejected(self):
        self.base()
        self.put([task('reused', True)])
        self.review()
        original = self.core.get(self.run_id, 'review')
        for key, value, message in [('criterion_ids', ['absent'], 'criterion'),
                ('task_requirements', [{'task_ref': f.r('reused'), 'requirement_ids': ['absent']}], 'ability IDs')]:
            with self.subTest(field=key):
                changed = HostIO.edit(original)
                changed['extensions']['capability_conditions']['cap']['understanding_basis'][0][key] = value
                from synframe_core.deliberation import review_errors
                errors = review_errors(self.core.get(self.run_id, 'goal'), self.core.get(self.run_id, 'candidate'),
                    changed, self.core.documents(self.run_id), lambda p: self.core.resolve(self.run_id, p))
                self.assertIn(message, ' '.join(errors))

    def test_unmet_ability_cannot_be_hidden_by_pass_and_valid_evidence(self):
        self.base()
        missing = task('missing')
        missing['assessment'].update(role='INDEPENDENT', materiality='NONMATERIAL', evidence_refs=[f.r('ev')])
        self.put([missing])
        gate = self.revise_review(lambda check: check['understanding_basis'][0].update(
            task_requirements=[{'task_ref': f.r('missing'), 'requirement_ids': ['ability']}]))
        self.assertFalse(gate['passed'])
        self.assertIn('unmet/unverified abilities', ' '.join(gate['errors']))

    def test_closed_task_reuse_has_actual_consumer_relationship_without_new_learning(self):
        self.base()
        self.put([task('reused', True), f.link('reuse-effect', [f.r('reused')], 'cap', 'REUSES')])
        gate = self.revise_review(lambda check: check['understanding_basis'][0].update(
            task_requirements=[{'task_ref': f.r('reused'), 'requirement_ids': ['ability']}]))
        self.assertTrue(gate['passed'])
        from synframe_core.deliberation import review_errors
        errors = review_errors(self.core.get(self.run_id, 'goal'), self.core.get(self.run_id, 'candidate'),
            self.core.get(self.run_id, 'review'),
            [d for d in self.core.documents(self.run_id) if d['id'] != 'reuse-effect'],
            lambda p: self.core.resolve(self.run_id, p))
        self.assertIn('missing consumption relationship', ' '.join(errors))
        self.assertEqual(self.core.get(self.run_id, 'reused')['revision'], 1)

    def test_using_one_grounded_ability_does_not_force_unrelated_learning_to_close(self):
        self.base()
        partial = task('partial')
        partial['assessment'].update(role='INDEPENDENT', materiality='NONMATERIAL', evidence_refs=[f.r('ev')])
        partial['answer_requirements'].append({**partial['answer_requirements'][0], 'id': 'unrelated'})
        partial['understanding']['abilities'] = [{'id': 'ability', 'status': 'MET',
            'evidence_refs': [f.r('ev')], 'rationale': 'Declared scoped reusable fixture discrimination'}]
        self.put([partial, f.link('partial-reuse', [f.r('partial')], 'cap', 'REUSES')])
        gate = self.revise_review(lambda check: check['understanding_basis'][0].update(
            task_requirements=[{'task_ref': f.r('partial'), 'requirement_ids': ['ability']}]))
        self.assertTrue(gate['passed'])
        self.assertEqual(self.core.get(self.run_id, 'partial')['disposition'], 'OPEN')

    def test_question_and_plan_consumer_alone_fail_atomically_with_observation_preserved(self):
        self.quality_setup()
        op, result = self.learning_result()
        raw = Path(self.temp.name) / 'raw.txt'
        raw.write_text('Actual synthetic observation awaiting relationship assessment')
        self.core.record_observation(self.run_id, op['id'], self.revision(), [{
            'path': str(raw), 'sha256': hashlib.sha256(raw.read_bytes()).hexdigest(), 'source': 'Isolated fixture'}])
        before = list(self.core.db.iterdump())
        for apply in (lambda: self.core.preflight(self.run_id, op['id'], result),
                      lambda: self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))):
            with self.assertRaisesRegex(f.ContractError, 'quality -> cap'):
                apply()
            self.assertEqual(before, list(self.core.db.iterdump()))
        self.assertTrue(self.core.get(self.run_id, op['id'])['extensions']['actual_observations'])

    def test_same_apply_relationship_creates_pending_obligation_and_survives_restore(self):
        self.quality_setup()
        op, result = self.learning_result([f.link('quality-effect', [f.r('quality', 2)], 'cap', 'AFFECTS')])
        self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        restored = self.core.restore(self.run_id)['status']
        pending = [o for o in restored['propagation_obligations'] if o['status'] == 'PENDING']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['target_ref'], f.r('cap'))
        self.assertEqual(self.core.get(self.run_id, 'cap')['revision'], 1)
        consumer = next(c for c in self.core.work_context(self.run_id)['requirements_context']['consumers']
                        if c['source']['declared_ref']['id'] == 'quality')
        self.assertEqual(consumer['relationship_ref'], f.r('quality-effect'))
        self.assertTrue(consumer['rationale'])

    def test_existing_relationship_is_reused_but_discovery_lineage_is_insufficient(self):
        self.quality_setup('DISCOVERED_FROM')
        op, result = self.learning_result(outcome='UNKNOWN')
        with self.assertRaisesRegex(f.ContractError, 'missing consumption relationship'):
            self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        # Repair the explicit declaration in the same unapplied result, not the observation or answer.
        result['proposed_state_changes'].append(f.link('actual-impact', [f.r('quality', 2)], 'cap', 'AFFECTS'))
        self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        self.assertEqual(self.core.work_context(self.run_id)['pending_propagation_count'], 1)

    def test_existing_effect_edge_not_a_new_link_is_accepted(self):
        self.quality_setup('AFFECTS')
        op, result = self.learning_result()
        self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        self.assertEqual(self.core.get(self.run_id, 'quality-effect')['revision'], 1)
        self.assertEqual(self.core.work_context(self.run_id)['pending_propagation_count'], 1)

    def test_same_apply_consumer_revision_still_needs_an_actual_effect_assessment(self):
        self.quality_setup()
        edge = f.link('quality-effect', [f.r('quality', 2)], 'cap', 'AFFECTS')
        edge['target_ref'] = f.r('cap', 2)
        op, result = self.learning_result([f.capability(), edge])
        self.core.apply(self.run_id, op['id'], self.core.prepare(self.run_id, op['id'], result))
        pending = [o for o in self.core.work_context(self.run_id)['propagation_obligations'] if o['status'] == 'PENDING']
        self.assertEqual(pending[0]['target_ref'], f.r('cap', 2))

    def test_evidence_projection_exposes_original_current_and_stale_consumer_without_rebinding(self):
        cap = f.capability()
        cap['provenance'] = [f.r('ev')]
        self.put([f.evidence(), cap])
        self.put([f.evidence(claim='Changed scoped fixture observation')])
        before = list(self.core.db.iterdump())
        context = self.core.work_context(self.run_id)['requirements_context']
        entry = next(e for e in context['evidence_bindings'] if e['owner_ref']['id'] == 'cap')
        self.assertEqual(entry['declared_ref'], f.r('ev'))
        self.assertEqual(entry['current_ref'], f.r('ev', 2))
        self.assertFalse(entry['reference_current'])
        self.assertEqual(context['capabilities'][0]['validity_status'], 'STALE')
        self.assertEqual(before, list(self.core.db.iterdump()))

    def test_completed_delivery_rechecks_changed_and_deleted_files_without_changing_state(self):
        self.base(); self.review(); self.commit()
        artifact = Path(self.temp.name) / 'result.txt'
        original = b'Verified fixture result'
        artifact.write_bytes(original)
        self.package(artifacts=[{'path': str(artifact), 'sha256': hashlib.sha256(original).hexdigest(),
                                 'source': 'Actual isolated fixture file'}])
        self.completion()
        io = HostIO(self.path, self.run_id)
        context = io.work_context()
        before = list(self.core.db.iterdump())
        artifact.write_text('Changed after completion')
        with self.assertRaisesRegex(ValueError, 'artifact changed after validation'):
            io.return_result(context, text='Explicit result')
        artifact.unlink()
        with self.assertRaisesRegex(ValueError, 'artifact is absent'):
            io.return_result(io.work_context(), text='Explicit result')
        self.assertEqual(before, list(self.core.db.iterdump()))
        self.assertEqual(self.core.status(self.run_id)['run']['state'], 'COMPLETED')

    def test_unreadable_artifact_is_reported_without_rewriting_it(self):
        artifact = Path(self.temp.name) / 'unreadable.txt'
        artifact.write_bytes(b'Original')
        record = {'path': str(artifact), 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'source': 'Fixture'}
        with mock.patch('synframe_core.files.file_sha256', side_effect=PermissionError('Fixture denied')):
            with self.assertRaisesRegex(ValueError, 'artifact cannot be read'):
                validate_artifacts([record])
        self.assertEqual(artifact.read_bytes(), b'Original')
