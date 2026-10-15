"""Delivery/application boundaries, never independent semantic quality proof."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

import test_core as fixtures
from test_learning import task,dep
from synframe_core.learning import basis
from synframe_host import HostIO,read_contract


class WorkLoopIOAcceptance(unittest.TestCase):
    setUp=fixtures.CoreAcceptance.setUp
    tearDown=fixtures.CoreAcceptance.tearDown
    request=fixtures.CoreAcceptance.request
    put=fixtures.CoreAcceptance.put
    revision=fixtures.CoreAcceptance.revision
    base=fixtures.CoreAcceptance.base

    def stored(self):return list(self.core.db.iterdump())
    def build(self,io,op,changes,**updates):
        args={'result_ids':[d['id'] for d in changes],'preserved_refs':[],
            'evidence_refs':[],'unresolved_items':[], 'observed_effects':['Declared fixture observation'],
            'next_decision_inputs':['Declared fixture next assessment'],'outcome':'SUCCEEDED',
            'learning_results':[],'propagation_resolutions':[],'path_assessments':[]}
        return io.build_result(op,changes,**(args|updates))

    def test_contract_chunks_roundtrip_all_unicode_text_and_reject_identity_drift(self):
        root=Path(self.temp.name)/'skill';root.mkdir();(root/'references').mkdir()
        content='계약 첫머리\n'+'중요한 조건과 다음 판단.\n'*2100+'마지막 계약 조건\n'
        (root/'SKILL.md').write_text(content,encoding='utf-8')
        manifest=read_contract(root);checksum=manifest['files'][0]['sha256']
        offset=0;chunks=[]
        while True:
            chunk=read_contract(root,'SKILL.md',offset,6000,checksum)
            self.assertLessEqual(len(chunk['text']),6000)
            self.assertEqual(chunk['chunk_sha256'],hashlib.sha256(chunk['text'].encode()).hexdigest())
            chunks.append(chunk['text'])
            if chunk['next_offset'] is None:break
            self.assertGreater(chunk['next_offset'],offset);offset=chunk['next_offset']
        self.assertEqual(''.join(chunks),content)
        (root/'SKILL.md').write_text(content+' changed')
        with self.assertRaisesRegex(ValueError,'contract changed'):read_contract(root,'SKILL.md',0,6000,checksum)
        for name,offset,limit in (('../outside',0,100),('SKILL.md',-1,100),('SKILL.md',0,6001)):
            with self.assertRaises(ValueError):read_contract(root,name,offset,limit)

    def test_contract_cli_is_state_free_even_with_a_run_and_reads_final_text(self):
        io=HostIO(self.path,self.run_id);before=self.stored()
        manifest=io.call('read-contract');entry=next(e for e in manifest['files'] if e['name']=='references/learning-contract.md')
        chunk=io.call('read-contract',name=entry['name'],offset=entry['characters']-150,expected_sha=entry['sha256'])
        self.assertIsNone(chunk['next_offset']);self.assertEqual(self.stored(),before)
        self.assertEqual(len(chunk['text']),150)

    def test_work_context_keeps_unapplied_receipts_open_questions_and_actual_consumers(self):
        self.put([fixtures.evidence(),task()])
        plan=copy.deepcopy(fixtures.interpretation_plan(self.core.get(self.run_id,'goal:goal-interpretation'))['learning_plan'][0])
        plan.update(task_ref=fixtures.r('task'),requirement_ids=['ability'])
        plan['judgment_target']['target_ref']=fixtures.r('task')
        op=self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',{
            'learning_task_refs':[fixtures.r('task')],'learning_plan':[plan]}))
        raw=Path(self.temp.name)/'pending-receipt.txt';raw.write_text('Synthetic actual observation awaiting host evaluation')
        io=HostIO(self.path,self.run_id)
        io.preserve_files(op,[{'path':str(raw),'source':'Declared fixture source'}],expected_revision=self.revision())
        before=self.stored();packet=io.work_context(op)
        self.assertEqual(before,self.stored())
        self.assertEqual(packet['state_digest'],self.core.observe(self.run_id)['state_digest'])
        self.assertEqual(packet['unapplied_observation_count'],1)
        self.assertEqual(packet['selected_tasks'][0]['current']['answer']['status'],'UNANSWERED')
        self.assertEqual(packet['consumers'][0]['current']['id'],'goal')
        self.assertTrue(packet['consumers'][0]['reference_current'])
        self.assertIsNone(packet['adoption']['committed_candidate_ref'])

    def test_build_is_read_only_finish_applies_and_does_not_fabricate_learning(self):
        io=HostIO(self.path,self.run_id);op=self.core.begin(self.run_id,self.request())
        change=fixtures.evidence('built-ev');before=self.stored()
        result=self.build(io,op,[change],outcome='UNKNOWN',observed_effects=['Declared uncertainty'])
        self.assertEqual(self.stored(),before);self.assertFalse(self.core.get(self.run_id,op['id'])['applied'])
        self.assertEqual(result['outcome'],'UNKNOWN');self.assertFalse(result['learning_results'])
        result['proposed_state_changes'][0]['claim']='Independent host-authored patch'
        self.assertNotEqual(change['claim'],result['proposed_state_changes'][0]['claim'])
        result['outcome']='SUCCEEDED';applied=io.finish(op,result)
        self.assertTrue(applied['applied']);self.assertTrue(io.work_context(op)['operation']['applied'])
        self.assertEqual(self.core.get(self.run_id,'built-ev')['claim'],'Independent host-authored patch')

    def test_build_requires_host_semantics_and_rejects_unselected_result_identity(self):
        io=HostIO(self.path,self.run_id);op=self.core.begin(self.run_id,self.request())
        with self.assertRaises(TypeError):io.build_result(op,[])
        with self.assertRaisesRegex(ValueError,'explicit distinct'):
            self.build(io,op,[fixtures.evidence()],result_ids=['absent'])
        self.assertFalse(self.core.get(self.run_id,op['id'])['applied'])

    def test_work_context_retains_unselected_assets_without_selecting_them(self):
        self.base();self.put([fixtures.asset('unused')])
        packet=self.core.work_context(self.run_id)
        self.assertEqual({a['asset_ref']['id'] for a in packet['assets']},{'asset','unused'})
        self.assertEqual(packet['candidates'][0]['asset_refs'],[fixtures.r('asset')])

    def test_partial_transition_does_not_hide_unassessed_available_work(self):
        self.put([fixtures.evidence(),task()]);op=self.core.begin(self.run_id,self.request())
        self.core.transition(self.run_id,'PARTIAL',self.revision(),'Declared transport fixture interruption')
        packet=self.core.work_context(self.run_id)
        self.assertEqual(packet['state'],'PARTIAL')
        self.assertTrue(packet['unfinished_learning']);self.assertTrue(packet['pending_operations'])
        self.assertFalse(packet['operation']);self.assertIsNone(packet['adoption']['result_package_ref'])

    def test_learning_handoff_changes_parent_candidate_and_exposes_next_consumption(self):
        self.base();parent=task('parent');parent.update(dependency_refs=[dep('child')],work_state='WAITING')
        self.put([parent,task('child'),fixtures.link('consumer-edge',[fixtures.r('parent')],'candidate','AFFECTS')])
        io=HostIO(self.path,self.run_id)
        for identity in ('child','parent'):
            old=self.core.get(self.run_id,identity)
            plan={'task_ref':io.reference(old),'parent_role':'Declared fixture prerequisite',
                'gap':'Declared open required ability','next_observation':{'target':identity,'source':'Synthetic observation',
                    'locator':'fixture receipt','information':'Declared condition','decision_effect':'Required fixture consumer'},
                'requirement_ids':['ability'],'known_evidence_refs':[fixtures.r('ev')],
                'judgment_target':{'target_ref':io.reference(old),'item_id':None,'decision':'Declared fixture ability',
                    'consumer_refs':[fixtures.r('candidate')],'scope':'Synthetic boundary check'},
                'sufficient_when':'Actual fixture ability and dependency recorded','failure_alternative':'Keep open'}
            op=self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',{'learning_task_refs':[io.reference(old)],'learning_plan':[plan]}))
            closed=task(identity,True)
            if identity=='parent':closed['dependency_refs']=[dep('child',2)]
            closed['closure_assessment']['basis']=basis(closed)
            changes=[closed]
            if identity=='parent':changes.append(fixtures.candidate(comparison_rationale='Declared child result consumed through parent'))
            resolutions=[{'id':o['id'],'assessment':'REVISE','evidence_refs':[fixtures.r('ev')],
                'rationale':'Declared child effect consumed by updated parent','result_refs':[fixtures.r('parent',2)],'remaining_work':[]}
                for o in io.work_context()['propagation_obligations'] if o['status']=='PENDING' and o['target_ref']['id']=='parent']
            learning=[{'task_ref':io.reference(old),'result_ref':fixtures.r(identity,2),'answer_refs':[fixtures.r('ev')],
                'understanding_change':'Declared sufficient fixture ability','discovery_ids':[],
                'upward_effects':['Declared actual consumer update'],'observations':['Fixture condition inspected'],
                'prediction_difference':'Declared fixture only'}]
            result=self.build(io,op,changes,learning_results=learning,propagation_resolutions=resolutions)
            io.finish(op,result)
        packet=io.work_context()
        self.assertFalse(packet['unfinished_learning'])
        self.assertEqual(packet['candidates'][0]['candidate_ref'],fixtures.r('candidate',2))
        self.assertIn('consumed through parent',packet['candidates'][0]['comparison_rationale'])
        self.assertFalse(packet['pending_operations'])
        self.assertFalse([o for o in packet['propagation_obligations'] if o['status']=='PENDING' and o['target_ref']['id']=='parent'])

    def test_bad_observation_shapes_fail_before_any_state_write(self):
        io=HostIO(self.path,self.run_id);op=self.core.begin(self.run_id,self.request());before=self.stored()
        for files in ([{'path':'absent','label':'missing source'}],['not a pair'],[('absent','')]):
            with self.assertRaises(ValueError):io.preserve_files(op,files,expected_revision=self.revision())
        self.assertEqual(self.stored(),before)

if __name__=='__main__':unittest.main()
