"""Structural obligation tests; declared judgments are not host-autonomy proof."""
import unittest
import copy
import hashlib
from pathlib import Path
import test_core as fixtures
from test_core import r, evidence, ContractError, output
from synframe_core.graph import reference
from synframe_core.learning import basis
from synframe_core import tool_obligations as duties


class ToolObligationAcceptance(unittest.TestCase):
    settle_scope_fixture = False
    setUp = fixtures.CoreAcceptance.setUp
    tearDown = fixtures.CoreAcceptance.tearDown
    revision = fixtures.CoreAcceptance.revision
    request = fixtures.CoreAcceptance.request
    put = fixtures.CoreAcceptance.put
    base = fixtures.CoreAcceptance.base
    review = fixtures.CoreAcceptance.review
    review_extensions = fixtures.CoreAcceptance.review_extensions

    def closed(self, saved, grounds, verdict='ANSWERED'):
        doc = {k:copy.deepcopy(v) for k,v in saved.items() if k not in {
            'revision','schema_version','created_at','updated_at','source_run_id','validity_status'}}
        doc['assessment'].update(relevance='NOT_RELEVANT' if verdict=='NOT_APPLICABLE' else 'RELEVANT',
            materiality='NONMATERIAL' if verdict=='NOT_APPLICABLE' else 'MATERIAL',
            evidence_refs=grounds, unknowns=[], rationale='Explicit structural fixture judgment, not autonomous evidence')
        doc['answer'].update(status='SUPPORTED', claims=[{'id':'answer','text':'Declared fixture answer',
            'evidence_refs':grounds,'source_locator':'fixture actual receipt','conditions':['Fixture only'],'inference':False}], gaps=[])
        doc['understanding'].update(status='SUFFICIENT',k_level=3,abilities=[{'id':need['id'],'status':'MET',
            'evidence_refs':grounds,'rationale':'Declared fixture assessment'} for need in doc['answer_requirements']])
        doc['expansion'].update(status='ACCOUNTED',scope_rationale='Declared fixture examined scope',evidence_refs=grounds)
        doc.update(disposition='CLOSED',work_state='IDLE')
        doc['extensions']['next_action']=None
        doc['closure_assessment']={'verdict':verdict,'rationale':'Declared fixture closure','evidence_refs':grounds,
            'scope':'Structural fixture','remaining_uncertainties':[],'basis':basis(doc)}
        return doc

    def applies(self):
        scope=self.core.get(self.run_id,'goal:tool-scope')
        self.put([evidence('scope-ev'),self.closed(scope,[r('scope-ev')])])

    def plan(self, saved):
        from synframe_core.learning import dependencies
        consumers=[edge.get('target_ref',reference(doc)) for doc in self.core.documents(self.run_id)
            for edge in dependencies(doc) if edge['source_ref']['id']==saved['id']
            and edge['role']!='DISCOVERED_FROM']
        return {'learning_task_refs':[reference(saved)],'learning_plan':[{
            'task_ref':reference(saved),'parent_role':'Contract responsibility in structural fixture',
            'gap':'Declared unfulfilled responsibility','requirement_ids':[n['id'] for n in saved['answer_requirements']],
            'known_evidence_refs':[],'judgment_target':{'target_ref':reference(saved),'item_id':None,
                'decision':'Assess declared fixture duty','consumer_refs':consumers or [reference(saved)],'scope':'Fixture only'},
            'next_observation':{'target':'Fixture observation','source':'Actual local fixture file',
                'locator':'fixture raw receipt','information':'Declared observation result','decision_effect':'Duty assessment'},
            'sufficient_when':'Actual fixture bindings present','failure_alternative':'Retain unanswered duty'}]}

    def finish_duty(self, role, receipt=True, wrong_source=False):
        saved=self.core.get(self.run_id,duties.identity('goal',role))
        action='DISCOVER_KNOWLEDGE' if role=='discovery' else 'EXPAND_COMPOSITION'
        op=self.core.begin(self.run_id,self.request(action,self.plan(saved)))
        raw=Path(self.temp.name)/(role+'-raw.txt');raw.write_text('Explicit synthetic observation, not autonomous host research')
        if receipt:
            self.core.record_observation(self.run_id,op['id'],self.revision(),[{'path':str(raw),
                'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source':'fixture observation '+role}])
        ev=evidence(role+'-ev',source='unrelated source' if wrong_source else str(raw))
        doc=self.closed(saved,[r(role+'-ev')])
        if role=='composition':
            doc['dependency_refs'][0]['source_ref']=reference(self.core.get(self.run_id,'goal:tool-discovery'))
            doc['closure_assessment']['basis']=basis(doc)
        result=output(op,[ev,doc],core=self.core)
        result['learning_results']=[{'task_ref':reference(saved),'result_ref':r(doc['id'],saved['revision']+1),
            'answer_refs':[r(role+'-ev')],'understanding_change':'Declared fixture abilities now supported',
            'discovery_ids':[],'upward_effects':['Actual fixture consumer assessment'],
            'observations':['Actual synthetic file was written and inspected'],
            'prediction_difference':'Fixture result, not an autonomy claim'}]
        if role=='composition':
            result['propagation_resolutions']=[{'id':o['id'],'assessment':'REVISE',
                'evidence_refs':[r(role+'-ev')],'rationale':'Declared fixture consumes current discovery revision',
                'result_refs':[r(doc['id'],saved['revision']+1)],'remaining_work':[]}
                for o in self.core.status(self.run_id)['propagation_obligations']
                if o['status']=='PENDING' and o['target_ref']['id']==doc['id']]
        return self.core.apply(self.run_id,op['id'],self.core.prepare(self.run_id,op['id'],result))

    def test_scope_registration_is_not_a_host_generated_answer(self):
        state = self.core.observe(self.run_id)
        scope = self.core.get(self.run_id, 'goal:tool-scope')
        self.assertEqual(scope['answer']['status'], 'UNANSWERED')
        self.assertEqual(scope['understanding']['status'], 'UNASSESSED')
        self.assertEqual(scope['disposition'], 'OPEN')
        self.assertIn('tool_obligations', state)

    def test_missing_scope_is_detected_without_review_check_declaration(self):
        from synframe_core.tool_obligations import gate_errors
        self.assertTrue(gate_errors(self.core.get(self.run_id, 'goal'), [], [], lambda p: None))

    def test_operating_identity_is_goal_scoped_not_question_wording(self):
        from synframe_core.tool_obligations import identity
        self.assertEqual(identity('goal', 'scope'), 'goal:tool-scope')
        self.assertNotEqual(identity('goal', 'discovery'), identity('other-goal', 'discovery'))

    def test_applicability_registers_both_unanswered_duties_and_feedback(self):
        self.applies()
        state=self.core.observe(self.run_id)
        self.assertTrue(state['tool_obligations']['applicable'])
        for role in ('discovery','composition'):
            task=self.core.get(self.run_id,duties.identity('goal',role))
            self.assertEqual(task['answer']['status'],'UNANSWERED')
            self.assertTrue(any(isinstance(i,dict) and i.get('task_ref')==reference(task) for i in state['last_result']['next_decision_inputs']))

    def test_generic_ready_cannot_hide_unperformed_tool_duties(self):
        self.applies();self.base()
        with self.assertRaisesRegex(ContractError,'Review tool obligations'):
            self.review()

    def test_missing_either_duty_is_detected_independently_of_review_keys(self):
        self.applies();goal=self.core.get(self.run_id,'goal')
        for role in ('discovery','composition'):
            docs=[d for d in self.core.documents(self.run_id) if d['id']!=duties.identity('goal',role)]
            errors=duties.gate_errors(goal,docs,[],lambda p:self.core.resolve(self.run_id,p))
            self.assertTrue(any('missing contractual tool obligation: '+role in e for e in errors))

    def test_duty_cannot_be_downgraded_to_independent_or_minor(self):
        self.applies()
        for key,value in [('role','INDEPENDENT'),('materiality','NONMATERIAL')]:
            doc=copy.deepcopy(self.core.get(self.run_id,'goal:tool-discovery'))
            for field in ('revision','schema_version','created_at','updated_at','source_run_id','validity_status'):doc.pop(field)
            doc['assessment'][key]=value;doc['assessment']['evidence_refs']=[r('scope-ev')]
            with self.assertRaisesRegex(ContractError,'cannot'):
                self.put([doc])

    def test_plan_or_wrong_source_cannot_substitute_for_actual_search(self):
        self.applies()
        with self.assertRaisesRegex(ContractError,'actual-search observation binding'):
            self.finish_duty('discovery',receipt=False)
        self.assertEqual(self.core.get(self.run_id,'goal:tool-discovery')['disposition'],'OPEN')

    def test_unrelated_evidence_cannot_use_a_real_receipt(self):
        self.applies()
        with self.assertRaisesRegex(ContractError,'actual-search observation binding') as rejected:
            self.finish_duty('discovery',wrong_source=True)
        details=rejected.exception.details
        self.assertEqual(details['task_ref'],r('goal:tool-discovery',2))
        self.assertEqual(details['ability_id'],'discovery.actual_search')
        self.assertEqual(details['evidence_sources'],[{'evidence_ref':r('discovery-ev'),'source':'unrelated source'}])
        self.assertEqual(details['allowed_observations'][0]['source'],'fixture observation discovery')
        self.assertEqual(details['allowed_observations'][0]['file_status'],'matching')
        self.assertEqual(self.core.get(self.run_id,'goal:tool-discovery')['disposition'],'OPEN')
        self.assertFalse(any(d['id']=='discovery-ev' for d in self.core.documents(self.run_id)))

    def test_receipt_path_and_source_bind_but_extension_cannot_replace_canonical_source(self):
        raw=Path(self.temp.name)/'search-observation.txt';raw.write_text('Actual synthetic search receipt')
        saved=self.core.get(self.run_id,'goal:tool-scope')
        saved['understanding']['abilities']=[{'id':'discovery.actual_search','status':'MET','evidence_refs':[r('search-ev')]}]
        receipt={'path':str(raw),'source':'explicit original source','sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
        operation={'id':'search-op','revision':1,'action':'DISCOVER_KNOWLEDGE','applied':True,
            'result':{'outcome':'SUCCEEDED'},'intent':{'learning_task_refs':[reference(saved)]},
            'extensions':{'actual_observations':[receipt]}}
        for source in (receipt['path'],receipt['source']):
            ev={**evidence('search-ev',source=source),'revision':1}
            self.assertTrue(duties.observation_binding(saved,[operation],lambda p:ev,raise_on_missing=True))
        ev={**evidence('search-ev',source='https://example.invalid/original',
            extensions={'observation_file':str(raw)}),'revision':1}
        self.assertFalse(duties.observation_binding(saved,[operation],lambda p:ev))
        with self.assertRaises(ContractError) as rejected:
            duties.observation_binding(saved,[operation],lambda p:ev,raise_on_missing=True)
        self.assertEqual(rejected.exception.details['evidence_sources'][0]['source'],ev['source'])
        raw.write_text('Changed raw source')
        with self.assertRaises(ContractError) as changed:
            duties.observation_binding(saved,[operation],lambda p:{**ev,'source':str(raw)},raise_on_missing=True)
        self.assertEqual(changed.exception.details['allowed_observations'][0]['file_status'],'hash_mismatch')

    def test_actual_search_does_not_complete_composition(self):
        self.applies();self.finish_duty('discovery')
        self.assertEqual(self.core.get(self.run_id,'goal:tool-discovery')['disposition'],'CLOSED')
        self.assertEqual(self.core.get(self.run_id,'goal:tool-composition')['disposition'],'OPEN')
        self.base()
        with self.assertRaisesRegex(ContractError,'Review tool obligations'):
            self.review()

    def test_current_discovery_and_composition_can_reach_gate(self):
        self.applies();self.finish_duty('discovery');self.finish_duty('composition');self.base();review=self.review()
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate'),review)['passed'])
        self.assertFalse(self.core.observe(self.run_id)['learning_frontier']['ready'])
        before=self.core.restore(self.run_id)
        self.assertEqual(before,self.core.restore(self.run_id))

    def test_discovery_catalog_tracks_current_task_without_becoming_proof(self):
        scope=self.core.get(self.run_id,'goal:tool-scope')
        doc=self.closed(scope,[r('scope-ev')])
        doc['expansion']['discoveries']=[{'id':'registered-duties','source_locator':'Fixture source',
            'content':'Register independent operating duties','observation_kind':'inference',
            'novelty':'New responsibilities','parent_connection':'Current goal',
            'understanding_gap':'Actual duties unfinished','assessment':'MATERIAL',
            'disposition':'CREATE_TASK','target_refs':[r('goal:tool-discovery'),r('goal:tool-composition')],
            'rationale':'Registration history, not a proof of applicability','reopen_condition':'Goal change'}]
        doc['closure_assessment']['basis']=basis(doc)
        self.put([evidence('scope-ev'),doc])
        self.finish_duty('discovery');self.finish_duty('composition');self.base()
        review=self.review()
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate'),review)['passed'])
        self.assertEqual(self.core.get(self.run_id,'goal:tool-scope')['expansion']['discoveries'][0]['target_refs'][0],r('goal:tool-discovery'))
        # Current duties remain independently required; historical registration
        # must not promote an unfinished current task or erase its responsibility.
        docs=[d for d in self.core.documents(self.run_id) if d['id']!='goal:tool-discovery']
        errors=duties.gate_errors(self.core.get(self.run_id,'goal'),docs,[],lambda p:self.core.resolve(self.run_id,p))
        self.assertTrue(any('missing contractual tool obligation: discovery' in e for e in errors))

    def test_changed_raw_receipt_blocks_an_existing_review(self):
        self.applies();self.finish_duty('discovery');self.finish_duty('composition');self.base();review=self.review()
        (Path(self.temp.name)/'discovery-raw.txt').write_text('Changed receipt')
        result=self.core.commit_gate(self.run_id,r('candidate'),review)
        self.assertFalse(result['passed'])
        self.assertIn('actual-search observation binding',' '.join(result['errors']))

    def test_final_composition_cannot_omit_unfinished_discovery(self):
        self.applies()
        with self.assertRaisesRegex(ContractError,'unfinished discovery'):
            self.finish_duty('composition')

    def test_nonapplicability_is_grounded_and_does_not_force_discovery(self):
        self.put(fixtures.declared_scope_fixture(self.core.get(self.run_id,'goal:tool-scope')))
        state=self.core.observe(self.run_id)
        self.assertFalse(state['tool_obligations']['applicable'])
        self.assertEqual(len(state['tool_obligations']['required']),1)
        self.base();review=self.review()
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate'),review)['passed'])

    def test_selected_asset_independent_improvement_can_be_groundedly_deferred(self):
        self.applies();self.finish_duty('discovery');self.finish_duty('composition')
        optional=fixtures.question('future-improvement','OPEN')
        optional['decision_impact']='Separate future use, not a premise of the measured current fixture function'
        self.put([evidence(),fixtures.capability(),fixtures.asset(understanding=[{'context':'Current fixture use',
            'level':3,'questions':[fixtures.question('current-use'),optional],'evidence_refs':[r('ev')],
            'stop_condition':'Current use grounded; independent future use separately assessed'}]),
            fixtures.link(),fixtures.candidate()])
        review=self.review()
        self.assertTrue(self.core.commit_gate(self.run_id,r('candidate'),review)['passed'])
        self.assertEqual(self.core.get(self.run_id,'asset-knowledge:0-future-improvement')['disposition'],'OPEN')

    def test_goal_revision_does_not_inherit_applicability_approval(self):
        self.applies()
        goal=fixtures.goal();goal['objective']='Revised original-purpose interpretation'
        self.put([goal],'GOAL_COMPILE',{'source_preservation_correction':'Fixture goal interpretation corrected'})
        errors=duties.gate_errors(self.core.get(self.run_id,'goal'),self.core.documents(self.run_id),[],lambda p:self.core.resolve(self.run_id,p))
        self.assertTrue(any('old goal' in e for e in errors))

    def test_nonapplicable_label_without_actual_assessment_is_rejected(self):
        changes=fixtures.declared_scope_fixture(self.core.get(self.run_id,'goal:tool-scope'))
        task=changes[-1]
        task['answer'].update(status='UNANSWERED',claims=[])
        task['understanding'].update(status='UNASSESSED',abilities=[],k_level=None)
        task['closure_assessment']['basis']=basis(task)
        with self.assertRaisesRegex(ContractError,'actual supported assessment'):
            self.put(changes)
        self.assertEqual(self.core.get(self.run_id,'goal:tool-scope')['disposition'],'OPEN')

    def test_duty_merge_cannot_drop_responsibility_abilities(self):
        self.applies()
        from test_learning import task as unrelated
        self.put([evidence(),unrelated('other',closed=True)])
        saved=self.core.get(self.run_id,'goal:tool-discovery')
        doc={k:copy.deepcopy(v) for k,v in saved.items() if k not in {
            'revision','schema_version','created_at','updated_at','source_run_id','validity_status'}}
        doc.update(disposition='CLOSED',work_state='IDLE')
        doc['closure_assessment']={'verdict':'REUSED','rationale':'Fixture attempted reuse of unrelated ability',
            'evidence_refs':[r('ev')],'basis':basis(doc),'scope':'Fixture','remaining_uncertainties':[],
            'target_ref':r('other'),'compatibility':'Declared fixture compatibility',
            'preserved_connections':doc['goal_connections']}
        with self.assertRaisesRegex(ContractError,'lost a required ability'):
            self.put([doc])


if __name__ == '__main__':
    unittest.main()
