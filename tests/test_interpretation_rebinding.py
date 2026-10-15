"""Declared current-consumer fixtures; not autonomous answer-quality evidence."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from test_core import r, evidence, candidate, output, ContractError
import test_goal_interpretation as interpretation_tests
import test_core as fixtures
from synframe_core.graph import reference
from synframe_core.learning import basis
from synframe_host import HostIO


class InterpretationRebindingAcceptance(unittest.TestCase):
    settle_interpretation_fixture = False
    setUp = interpretation_tests.GoalInterpretationAcceptance.setUp
    tearDown = interpretation_tests.GoalInterpretationAcceptance.tearDown
    revision = interpretation_tests.GoalInterpretationAcceptance.revision
    request = interpretation_tests.GoalInterpretationAcceptance.request
    put = interpretation_tests.GoalInterpretationAcceptance.put
    base = interpretation_tests.GoalInterpretationAcceptance.base
    task = interpretation_tests.GoalInterpretationAcceptance.task
    errors = interpretation_tests.GoalInterpretationAcceptance.errors
    finish = interpretation_tests.GoalInterpretationAcceptance.finish
    review_extensions = fixtures.CoreAcceptance.review_extensions

    def closed_consumer(self):
        self.base()
        def consume(doc):
            review = doc['extensions']['interpretation_review']
            review['interpretations'][0]['consumer_refs'] = [r('candidate')]
            review['effects'][0]['target_ref'] = r('candidate')
        self.finish(consume)
        old = copy.deepcopy(self.task())
        self.put([candidate(comparison_rationale='Synthetic current candidate; proof unchanged')], 'SIMPLIFY')
        return old

    def rebind(self, mutate=None, receipt=True, use_old_file=False, copy_old_bytes=False):
        old = self.task()
        op = self.core.begin(self.run_id, self.request('SIMPLIFY', {'interpretation_rebind':{
            'task_ref':reference(old),'rationale':'Synthetic consumer version comparison; unchanged assessment'}}))
        raw = Path(self.temp.name) / ('two-paths.txt' if use_old_file else 'current-consumer-'+op['id']+'.txt')
        if not use_old_file:
            raw.write_text('Synthetic actual consumer comparison against '+str(reference(self.core.get(self.run_id,'candidate')))
                           +'; no autonomous inference')
        if copy_old_bytes:
            raw.write_bytes((Path(self.temp.name)/'two-paths.txt').read_bytes())
        if receipt:
            self.core.record_observation(self.run_id,op['id'],self.revision(),[{
                'path':str(raw),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source':str(raw)}])
        consumer = reference(self.core.get(self.run_id,'candidate'))
        ev = evidence('consumer-comparison-'+op['id'],source=str(raw),extensions={'consumer_comparison':{
            'consumer_refs':[consumer],'assessment':'MAINTAIN','rationale':'Declared current consumption assessment'}})
        doc = HostIO.edit(old)
        review = doc['extensions']['interpretation_review']
        review['interpretations'][0]['consumer_refs'] = [consumer]
        review['effects'][0].update(target_ref=consumer,evidence_refs=[r(ev['id'])])
        if mutate:mutate(doc,ev)
        doc['closure_assessment']['basis'] = basis(doc)
        result = output(op,[ev,doc],core=self.core)
        result['evidence_refs'] = [r(ev['id'])]
        result['result_refs'] = list(self.core.patch_refs(self.run_id,[ev,doc])['refs'].values())
        checked = self.core.preflight(self.run_id,op['id'],result)
        self.core.apply(self.run_id,op['id'],checked['prepared_result'])
        applied = self.core.get(self.run_id,op['id'])
        return op,applied

    def test_closed_assessment_rebinds_same_run_without_learning_or_reopening(self):
        old = self.closed_consumer()
        self.assertTrue(self.errors())
        op, applied = self.rebind()
        self.assertFalse(self.errors())
        self.assertEqual(self.task()['answer'],old['answer'])
        self.assertEqual(self.task()['understanding'],old['understanding'])
        self.assertEqual(self.task()['disposition'],'CLOSED')
        self.assertFalse(applied['result']['learning_results'])
        self.assertFalse(self.core.restore(self.run_id)['status']['learning_frontier']['ready'])
        self.assertTrue(self.core.apply(self.run_id,op['id'],applied['result'])['duplicate'])
        self.assertEqual(self.core.get(self.run_id,old['id'],old['revision']),old)

    def test_rebinding_requires_fresh_observation_and_rejects_old_receipt(self):
        for receipt,oldfile in ((False,False),(True,True)):
            with self.subTest(receipt=receipt,oldfile=oldfile):
                if not hasattr(self,'created'):self.closed_consumer();self.created=True
                with self.assertRaisesRegex(ContractError,'fresh located'):
                    self.rebind(receipt=receipt,use_old_file=oldfile)

    def test_rebinding_does_not_replace_changed_claim_ability_k_or_scope(self):
        self.closed_consumer()
        for change in (lambda d,e:d['answer']['claims'][0].update(text='Different claim'),
                       lambda d,e:d['understanding'].update(k_level=4),
                       lambda d,e:d['context'].update(scope='Different scope'),
                       lambda d,e:d['extensions']['interpretation_review']['omission'].update(source_locator='New comparison'),
                       lambda d,e:d['answer_requirements'][0].update(ability='Different required ability')):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ContractError,'changed knowledge/scope'):self.rebind(change)

    def test_rebinding_rejects_wrong_consumer_scope_and_unperformed_effect(self):
        self.closed_consumer()
        with self.assertRaisesRegex(ContractError,'fresh located'):
            self.rebind(lambda d,e:e['extensions']['consumer_comparison'].update(consumer_refs=[r('goal')]))
        with self.assertRaisesRegex(ContractError,'only records grounded'):
            self.rebind(lambda d,e:d['extensions']['interpretation_review']['effects'][0].update(assessment='REVISE'))

    def test_preserved_comparison_tampering_still_blocks_rebinding(self):
        self.closed_consumer()
        (Path(self.temp.name)/'two-paths.txt').write_text('Tampered source comparison')
        with self.assertRaisesRegex(ContractError,'preserved actual comparison binding'):self.rebind()

    def test_copied_original_receipt_at_new_path_is_not_fresh_consumption(self):
        self.closed_consumer()
        with self.assertRaisesRegex(ContractError,'fresh located'):self.rebind(copy_old_bytes=True)

    def test_later_receipt_reuse_does_not_retroactively_invalidate_rebinding(self):
        self.closed_consumer();_,applied=self.rebind()
        receipt=applied['extensions']['actual_observations']
        op=self.core.begin(self.run_id,self.request('SIMPLIFY',{'task':'Later unrelated inspection'}))
        self.core.record_observation(self.run_id,op['id'],self.revision(),receipt)
        self.assertFalse(self.errors())

    def test_fresh_consumer_receipt_tampering_blocks_gate_after_rebinding(self):
        self.closed_consumer();op,_=self.rebind()
        (Path(self.temp.name)/('current-consumer-'+op['id']+'.txt')).write_text('Tampered current comparison')
        self.assertTrue(self.errors())

    def test_repeated_consumers_rebind_to_original_learning_without_fake_progress(self):
        old=self.closed_consumer();self.rebind()
        self.put([candidate(comparison_rationale='Next synthetic consumer version')],'SIMPLIFY')
        self.rebind();self.assertFalse(self.errors())
        self.assertEqual(self.task()['understanding'],old['understanding'])
        self.assertEqual(self.task()['extensions']['interpretation_review']['effects'][0]['target_ref'],r('candidate',3))

    def test_rebinding_requires_new_review_and_preserves_real_gap_gate(self):
        self.closed_consumer();self.rebind()
        checks={key:{'status':'PASS','rationale':'Declared fixture only','evidence_refs':[r('ev')]}
                for key in fixtures.REVIEW_CHECKS|{'constraint:skill'}}
        doc={'id':'current-review','type':'ReviewRecord','candidate_ref':r('candidate',2),'goal_ref':r('goal'),
             'snapshot':self.core.snapshot(self.run_id,r('candidate',2)),'checks':checks,'unresolved_items':[],
             'extensions':self.review_extensions()}
        self.put([doc],'REVIEW_SOLUTION')
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate',2),r('current-review'))['passed'])
        self.put([candidate(gaps=['Synthetic important unresolved condition'])],'SIMPLIFY')
        self.assertFalse(self.core.commit_gate(self.run_id,r('candidate',3),r('current-review'))['passed'])

    def test_undeclared_closed_copy_and_closed_learning_scheduling_remain_rejected(self):
        self.closed_consumer()
        with self.assertRaisesRegex(ContractError,'ended/paused'):
            self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',{'learning_task_refs':[reference(self.task())]}))
        with self.assertRaisesRegex(ContractError,'only for the closed'):
            self.core.begin(self.run_id,self.request('SIMPLIFY',{'interpretation_rebind':{
                'task_ref':r('goal:tool-scope',2),'rationale':'Wrong responsibility'}}))

if __name__ == '__main__':unittest.main()
