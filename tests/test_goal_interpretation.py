"""Declared fault/positive controls, not autonomous interpretation-quality proof."""
import copy,hashlib,json,unittest
from pathlib import Path
import test_core as fixtures
from test_core import r,evidence,output,ContractError,interpretation_plan,declared_interpretation_fixture
from synframe_core.graph import reference
from synframe_core.learning import basis
from synframe_core import goal_interpretation as review

class GoalInterpretationAcceptance(unittest.TestCase):
    settle_interpretation_fixture=False
    setUp=fixtures.CoreAcceptance.setUp
    tearDown=fixtures.CoreAcceptance.tearDown
    revision=fixtures.CoreAcceptance.revision
    request=fixtures.CoreAcceptance.request
    put=fixtures.CoreAcceptance.put
    base=fixtures.CoreAcceptance.base
    review=fixtures.CoreAcceptance.review
    review_extensions=fixtures.CoreAcceptance.review_extensions

    def task(self):return self.core.get(self.run_id,review.identity('goal'))
    def errors(self,docs=None):
        return review.gate_errors(self.core.get(self.run_id,'goal'),self.core.documents(self.run_id) if docs is None else docs,
            [json.loads(row[0]) for row in self.core.db.execute('SELECT data FROM operations WHERE run_id=?',(self.run_id,))],
            lambda p:self.core.resolve(self.run_id,p))
    def finish(self,mutate=None,receipt=True,wrong=False,conditional=False):
        saved=self.task();raw=Path(self.temp.name)/'two-paths.txt'
        changes=declared_interpretation_fixture(saved,'unrelated' if wrong else str(raw),conditional)
        doc=changes[-1]
        if mutate:mutate(doc)
        doc['closure_assessment']['basis']=basis(doc)
        plan=interpretation_plan(saved)
        # Declared fixture effects determine its actual consumers before intent.
        plan['learning_plan'][0]['judgment_target']['consumer_refs']=[
            e['target_ref'] for e in doc['extensions']['interpretation_review']['effects']]
        op=self.core.begin(self.run_id,self.request('DERIVE_CAPABILITY',plan))
        raw.write_text('Synthetic source support\nSynthetic omission comparison\n')
        if receipt:self.core.record_observation(self.run_id,op['id'],self.revision(),[{'path':str(raw),
            'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source':'Synthetic comparison'}])
        result=output(op,changes,core=self.core)
        result['learning_results']=[{'task_ref':reference(saved),'result_ref':r(saved['id'],saved['revision']+1),
            'answer_refs':[r('fixture-interpretation-ev')],'understanding_change':'Declared synthetic assessment',
            'discovery_ids':[d['id'] for d in doc['expansion']['discoveries']],
            'upward_effects':['Declared current consumer result'],'observations':['Synthetic receipt inspected'],
            'prediction_difference':'Declared fault or positive control; not autonomous inference'}]
        return self.core.apply(self.run_id,op['id'],self.core.prepare(self.run_id,op['id'],result))

    def test_initial_review_is_unanswered_not_generated_sufficiency(self):
        t=self.task();self.assertEqual((t['answer']['status'],t['understanding']['status'],t['disposition']),('UNANSWERED','UNASSESSED','OPEN'))
        self.assertTrue(any(x['task_ref']==reference(t) for x in self.core.observe(self.run_id)['learning_frontier']['ready']))
        self.assertFalse(self.core.observe(self.run_id)['goal_interpretation']['omission_recorded'])
    def test_expected_review_missing_independent_of_review_keys(self):
        self.assertIn('missing expected goal interpretation',self.errors([d for d in self.core.documents(self.run_id) if d['id']!=self.task()['id']])[0])
    def test_ready_cannot_hide_initial_review(self):
        self.base()
        with self.assertRaisesRegex(ContractError,'Review goal interpretation'):self.review()
    def test_support_only_cannot_close_review(self):
        with self.assertRaisesRegex(ContractError,'missing independent interpretation path: omission'):
            self.finish(lambda d:d['extensions']['interpretation_review'].pop('omission'))
        self.assertEqual(self.task()['disposition'],'OPEN')
    def test_copied_positive_path_cannot_substitute_for_omission(self):
        def change(d):
            x=d['extensions']['interpretation_review'];x['omission'].update(target=x['support']['target'],source_locator=x['support']['source_locator'])
        with self.assertRaisesRegex(ContractError,'positive support cannot substitute'):self.finish(change)
    def test_counterfactual_scope_cannot_be_omitted(self):
        with self.assertRaisesRegex(ContractError,'counterfactual_scope'):self.finish(lambda d:d['extensions']['interpretation_review']['omission'].pop('counterfactual_scope'))
    def test_raw_source_reverse_comparison_required(self):
        with self.assertRaisesRegex(ContractError,'source_to_result'):self.finish(lambda d:d['extensions']['interpretation_review']['omission'].pop('source_to_result'))
    def test_intent_only_is_not_actual_comparison(self):
        with self.assertRaisesRegex(ContractError,'preserved actual comparison binding'):self.finish(receipt=False)
    def test_unrelated_evidence_cannot_use_real_comparison_receipt(self):
        with self.assertRaisesRegex(ContractError,'preserved actual comparison binding'):self.finish(wrong=True)
    def test_current_clear_interpretation_can_close_without_external_search_or_plural_frames(self):
        self.finish();self.assertFalse(self.errors());self.base();rr=self.review()
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate'),rr)['passed'])
        self.assertFalse(self.core.observe(self.run_id)['learning_frontier']['ready'])
    def test_constructed_conditional_treatment_does_not_require_unique_intent(self):
        self.finish(conditional=True);self.assertFalse(self.errors())
        self.assertEqual(self.task()['extensions']['interpretation_review']['handling'],'CONDITIONAL')
    def test_formal_conditional_label_without_construction_rejected(self):
        with self.assertRaisesRegex(ContractError,'actual branch constructions'):
            self.finish(lambda d:d['extensions']['interpretation_review'].update(handling='CONDITIONAL',conditional_results=[]))
    def test_unresolved_processing_cannot_close(self):
        with self.assertRaisesRegex(ContractError,'remains unresolved'):self.finish(lambda d:d['extensions']['interpretation_review'].update(handling='UNRESOLVED'))
    def test_required_review_cannot_be_excluded_or_demoted(self):
        for change in [('role','INDEPENDENT'),('materiality','NONMATERIAL')]:
            with self.subTest(change=change):
                with self.assertRaisesRegex(ContractError,'cannot'):self.finish(lambda d:d['assessment'].update({change[0]:change[1]}))
    def test_required_ability_cannot_be_removed(self):
        def change(d):
            d['answer_requirements']=d['answer_requirements'][:-1];d['understanding']['abilities']=d['understanding']['abilities'][:-1]
            d['extensions']['requirements_change']={'rationale':'Synthetic attempted reduction','evidence_refs':[r('fixture-interpretation-ev')]}
        with self.assertRaisesRegex(ContractError,'lost required abilities'):self.finish(change)
    def test_noncurrent_consumer_reference_blocks_closure(self):
        with self.assertRaisesRegex(ContractError,'missing entity'):self.finish(lambda d:d['extensions']['interpretation_review']['effects'][0].update(target_ref=r('absent-consumer')))
    def test_unprocessed_consumer_effect_blocks_closure(self):
        with self.assertRaisesRegex(ContractError,'unprocessed consumer effects'):self.finish(lambda d:d['extensions']['interpretation_review']['effects'][0].update(assessment='NEEDS_OBSERVATION'))
    def test_omission_source_facet_loss_blocks_closure(self):
        with self.assertRaisesRegex(ContractError,'lost source facets'):self.finish(lambda d:d['extensions']['interpretation_review']['omission'].update(facet_ids=[]))
    def test_unknown_difference_requires_scoping_not_closed_label(self):
        def change(d):
            d['expansion']['discoveries']=[{'id':'unknown-difference','source_locator':'Synthetic observation','content':'Potential scope difference',
                'observation_kind':'inference','novelty':'Source use may differ','parent_connection':'Original purpose','understanding_gap':'Impact unresolved',
                'assessment':'UNKNOWN','disposition':'CREATE_TASK','target_refs':[r('child')],'rationale':'Needs actual scoping','reopen_condition':'Current'}]
            d['extensions']['interpretation_review']['omission']['difference_ids']=['unknown-difference']
        from test_learning import task
        self.put([evidence(),task('child')])
        with self.assertRaisesRegex(ContractError,'unassessed important difference'):self.finish(change)
    def test_receipt_tampering_blocks_existing_gate(self):
        self.finish();(Path(self.temp.name)/'two-paths.txt').write_text('Changed actual comparison receipt')
        self.assertIn('actual comparison binding',' '.join(self.errors()))
    def test_goal_revision_cannot_inherit_old_interpretation(self):
        self.finish();g=fixtures.goal();g['objective']='Refined source outcome'
        self.put([g],'GOAL_COMPILE',{'source_preservation_correction':'Declared source interpretation correction'})
        self.assertIn('old goal',' '.join(self.errors()))
    def test_two_path_record_is_bound_to_closure_basis(self):
        self.finish();doc={k:copy.deepcopy(v) for k,v in self.task().items() if k not in {
            'revision','schema_version','created_at','updated_at','source_run_id','validity_status'}}
        doc['extensions']['interpretation_review']['omission']['counterfactual_scope']='Changed located comparison'
        with self.assertRaisesRegex(ContractError,'stale snapshot'):self.put([doc])
    def test_unassessed_actual_observation_restores_without_success(self):
        saved=self.task();op=self.core.begin(self.run_id,self.request('DERIVE_CAPABILITY',interpretation_plan(saved)))
        raw=Path(self.temp.name)/'pending.txt';raw.write_text('Synthetic actual comparison not assessed')
        self.core.record_observation(self.run_id,op['id'],self.revision(),[{'path':str(raw),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source':'Synthetic source'}])
        state=self.core.restore(self.run_id)['status'];self.assertEqual(self.task()['answer']['status'],'UNANSWERED')
        self.assertEqual(len(state['pending_operations']),1);self.assertFalse(state['goal_interpretation']['omission_recorded'])
    def test_revise_label_without_actual_consumer_change_is_not_consumption(self):
        with self.assertRaisesRegex(ContractError,'actual comparison binding'):
            self.finish(lambda d:d['extensions']['interpretation_review']['effects'][0].update(assessment='REVISE'))
    def test_sufficient_review_restores_ended_without_rescheduling(self):
        self.finish();state=self.core.restore(self.run_id)['status']
        self.assertFalse(state['learning_frontier']['ready']);self.assertEqual(state['goal_interpretation']['answer_state'],'SUPPORTED')

if __name__=='__main__':unittest.main()
