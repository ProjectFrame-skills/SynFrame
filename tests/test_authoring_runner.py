"""Explicit serialization/recording fixtures, never autonomous host judgments."""
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_core as f
from synframe_host import HostIO, HostError
from synframe_author import execute, input_contract


class AuthoringRunnerAcceptance(unittest.TestCase):
    setUp = f.CoreAcceptance.setUp
    tearDown = f.CoreAcceptance.tearDown
    revision = f.CoreAcceptance.revision
    request = f.CoreAcceptance.request
    put = f.CoreAcceptance.put
    base = f.CoreAcceptance.base
    review = f.CoreAcceptance.review
    review_extensions = f.CoreAcceptance.review_extensions

    def io(self):
        return HostIO(self.path, self.run_id)

    def observed(self, op=None):
        context = self.io().work_context(op)
        return {key:context[key] for key in ('revision','state_digest')}

    def payload(self, op, changes):
        return {'operation_ref':HostIO.reference(op), 'observed_state':self.observed(op),
            'changes':changes, 'result_ids':[doc.get('id', doc.get('base_ref',{}).get('id')) for doc in changes],
            'preserved_refs':[], 'evidence_refs':[], 'unresolved_items':['Declared fixture pending work'],
            'observed_effects':['Actual fixture input retained'], 'next_decision_inputs':['Reassess actual saved fixture'],
            'outcome':'UNKNOWN', 'learning_results':[], 'propagation_resolutions':[], 'path_assessments':[]}

    def invoke(self, command, raw, *options):
        args=[sys.executable,str(f.SCRIPTS/'synframe_author.py'),'--state',str(self.path),
            '--run',self.run_id,*options,command,'--input','-']
        return subprocess.run(args,input=raw,text=True,capture_output=True)

    def test_begin_keeps_exact_observation_and_rejects_stale_judgment_without_stamping(self):
        request=self.request()
        payload={'action':request['action'],'judgment':request['decision'],'intent':request['intent'],
            'input_refs':request['input_refs'],'evidence_refs':request['evidence_refs'],'key':request['idempotency_key']}
        original=copy.deepcopy(payload)
        op=execute(self.io(),'begin',payload)
        self.assertEqual(payload,original)
        before=list(self.core.db.iterdump())
        payload['key']='new-stale-key'
        with self.assertRaisesRegex(HostError,'revision conflict|fresh observe'):
            execute(self.io(),'begin',payload)
        # Core intentionally preserves rejected intent history without changing
        # run/entity/operation state or approving the stale judgment.
        after=list(self.core.db.iterdump())
        self.assertEqual([line for line in before if not line.startswith(('INSERT INTO "events"','INSERT INTO "sqlite_sequence"'))],
            [line for line in after if not line.startswith(('INSERT INTO "events"','INSERT INTO "sqlite_sequence"'))])
        self.assertEqual(self.core.db.execute('SELECT kind FROM events ORDER BY seq DESC LIMIT 1').fetchone()[0],
            'REJECTED_INTENT')
        self.assertFalse(op['applied'])
        bad={**payload,'input_refs':None}
        with self.assertRaisesRegex(ValueError,'explicit input_refs'):
            execute(self.io(),'begin',bad)

    def test_result_requires_all_explicit_judgments_and_does_not_default_missing_values(self):
        op=self.core.begin(self.run_id,self.request())
        payload=self.payload(op,[f.evidence('added')]);before=list(self.core.db.iterdump())
        for key in ('unresolved_items','outcome','next_decision_inputs','learning_results'):
            invalid=copy.deepcopy(payload);del invalid[key]
            with self.assertRaisesRegex(ValueError,key):execute(self.io(),'result',invalid)
        self.assertEqual(before,list(self.core.db.iterdump()))
        result=execute(self.io(),'result',payload)
        saved=self.core.get(self.run_id,op['id'])['result']
        self.assertTrue(result['applied'])
        self.assertEqual(saved['outcome'],'UNKNOWN')
        self.assertIn('Declared fixture pending work',saved['unresolved_items'])
        self.assertEqual(self.core.status(self.run_id)['run']['state'],'ACTIVE')

    def test_build_is_read_only_and_finish_uses_the_exact_explicit_materialized_result(self):
        op=self.core.begin(self.run_id,self.request())
        payload=self.payload(op,[f.evidence('added')]);before=list(self.core.db.iterdump())
        built=execute(self.io(),'build-result',payload)
        self.assertEqual(before,list(self.core.db.iterdump()))
        finish={'operation_ref':HostIO.reference(op),'observed_state':payload['observed_state'],'result':built}
        applied=execute(self.io(),'finish',finish)
        self.assertTrue(applied['applied'])
        before=list(self.core.db.iterdump())
        repeated=execute(self.io(),'finish',finish)
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(before,list(self.core.db.iterdump()))
        changed=copy.deepcopy(built);changed['unresolved_items']=[]
        with self.assertRaisesRegex(HostError,'already applied'):
            execute(self.io(),'finish',{'operation_ref':HostIO.reference(op),
                'observed_state':payload['observed_state'],'result':changed})

    def test_exact_base_dictionary_edits_preserve_original_and_replace_whole_lists(self):
        self.put([f.evidence('base',environment={'items':['old'],'keep':True})])
        saved=self.core.get(self.run_id,'base');original=copy.deepcopy(saved)
        delta={'base_ref':HostIO.reference(saved),
            'replacements':[{'path':['environment','items'],'value':['new','explicit']},
                            {'path':['claim'],'value':'Changed synthetic claim'}],
            'removals':[['environment','keep']]}
        op=self.core.begin(self.run_id,self.request())
        result=execute(self.io(),'result',self.payload(op,[delta]))
        current=self.core.get(self.run_id,'base')
        self.assertEqual(current['environment'],{'items':['new','explicit']})
        self.assertEqual(current['claim'],'Changed synthetic claim')
        self.assertEqual(saved,original)
        self.assertEqual(HostIO.result_ref(result,'base'),f.r('base',2))
        another=self.core.begin(self.run_id,self.request())
        before=list(self.core.db.iterdump())
        with self.assertRaisesRegex(ValueError,'exact retained base'):
            execute(self.io(),'result',self.payload(another,[delta]))
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_field_edits_reject_implicit_list_merges_identity_changes_and_overlapping_paths(self):
        saved=self.core.get(self.run_id,'goal:goal-interpretation')
        def edit(replacements,removals=None):
            return HostIO.edit_fields(saved,expected_ref=HostIO.reference(saved),
                replacements=replacements,removals=[] if removals is None else removals)
        for path in [['revision'],['id'],['type'],['understanding','abilities','0','status']]:
            with self.assertRaises(ValueError):edit([{'path':path,'value':'invented'}])
        with self.assertRaisesRegex(ValueError,'overlapping'):
            edit([{'path':['answer'],'value':{}},{'path':['answer','status'],'value':'SUPPORTED'}])
        with self.assertRaisesRegex(ValueError,'does not exist'):
            edit([], [['extensions','absent']])
        with self.assertRaisesRegex(ValueError,'parent does not exist'):
            edit([{'path':['extensions','absent','new'],'value':True}])

    def test_material_edit_does_not_refresh_closed_learning_basis_or_approve_new_gap(self):
        saved=self.core.get(self.run_id,'goal:goal-interpretation')
        delta={'base_ref':HostIO.reference(saved),
            'replacements':[{'path':['answer','gaps'],'value':['New unresolved fixture condition']}], 'removals':[]}
        op=self.core.begin(self.run_id,self.request());payload=self.payload(op,[delta])
        before=list(self.core.db.iterdump());built=execute(self.io(),'build-result',payload)
        task=built['proposed_state_changes'][0]
        self.assertEqual(task['closure_assessment'],saved['closure_assessment'])
        self.assertEqual(task['understanding'],saved['understanding'])
        with self.assertRaises(HostError):
            execute(self.io(),'finish',{'operation_ref':HostIO.reference(op),
                'observed_state':payload['observed_state'],'result':built})
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_observed_state_and_projection_changes_are_rejected_without_rebase(self):
        op=self.core.begin(self.run_id,self.request());payload=self.payload(op,[f.evidence('added')])
        self.core.begin(self.run_id,self.request('SIMPLIFY'))
        before=list(self.core.db.iterdump())
        with self.assertRaisesRegex(ValueError,'observed state changed'):
            execute(self.io(),'result',payload)
        self.assertEqual(before,list(self.core.db.iterdump()))
        def change_after_read(changes):
            self.core.begin(self.run_id,self.request('SIMPLIFY'))
            return self.io().patch_refs(changes)
        payload['observed_state']=self.observed(op)
        io=self.io()
        with patch.object(io,'patch_refs',side_effect=change_after_read):
            with self.assertRaisesRegex(ValueError,'projection changed'):
                execute(io,'build-result',payload)
        self.assertFalse(self.core.get(self.run_id,op['id'])['applied'])

    def test_selected_full_documents_share_context_revision_and_do_not_mutate_state(self):
        self.put([f.evidence('first'),f.evidence('second')]);before=list(self.core.db.iterdump())
        existing=self.core.work_context(self.run_id)
        self.assertNotIn('documents',existing)
        view=self.io().work_context(document_ids=['second','first'])
        self.assertEqual(view['revision'],existing['revision'])
        self.assertEqual(view['state_digest'],existing['state_digest'])
        self.assertEqual(view['documents'],[self.core.get(self.run_id,x) for x in ['second','first']])
        self.assertEqual(before,list(self.core.db.iterdump()))
        for values in [[],['first','first'],['missing'],[None]]:
            with self.assertRaises(HostError):self.io().work_context(document_ids=values)

    def test_cli_preserves_original_failure_and_corrected_invocations_separately(self):
        request=self.request()
        bad='{"action":"DERIVE_CAPABILITY","action":"SIMPLIFY"}'
        failed=self.invoke('begin',bad)
        self.assertEqual(failed.returncode,2)
        error=json.loads(failed.stderr);folder=Path(error['record_dir'])
        self.assertEqual((folder/'input.json').read_text(),bad)
        self.assertIn('duplicate JSON key',error['message'])
        payload={'action':request['action'],'judgment':request['decision'],'intent':request['intent'],
            'input_refs':request['input_refs'],'evidence_refs':request['evidence_refs'],'key':request['idempotency_key']}
        passed=self.invoke('begin',json.dumps(payload),'--receipt-only')
        self.assertEqual(passed.returncode,0,passed.stderr)
        receipt=json.loads(passed.stdout);output=Path(receipt['output_file'])
        self.assertNotEqual(output.parent,folder)
        self.assertEqual(receipt['output_sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual((folder/'input.json').read_text(),bad)
        self.assertTrue((folder/'error.json').is_file())
        self.assertFalse(json.loads(output.read_text())['applied'])

    def test_cli_location_guards_precede_any_journal_write_including_symlink_paths(self):
        forbidden=f.SCRIPTS.parent/'author-test-forbidden'
        raw='{}'
        result=subprocess.run([sys.executable,str(f.SCRIPTS/'synframe_author.py'),
            '--state',str(forbidden),'--run',self.run_id,'begin','--input','-'],
            input=raw,text=True,capture_output=True)
        self.assertEqual(result.returncode,2);self.assertFalse(forbidden.exists())
        link=self.path/'skill-link';link.symlink_to(f.SCRIPTS.parent,target_is_directory=True)
        result=self.invoke('begin',raw,'--records',str(link/'author-test-forbidden'))
        self.assertEqual(result.returncode,2);self.assertFalse(forbidden.exists())

    def test_preserved_files_keep_actual_bytes_and_completion_has_no_automatic_pass(self):
        op=self.core.begin(self.run_id,self.request());raw=self.path/'raw.json';raw.write_text('Actual fixture observation')
        saved=execute(self.io(),'preserve-files',{'operation_ref':HostIO.reference(op),
            'files':[{'path':str(raw),'source':'Synthetic observation fixture'}]})
        self.assertEqual(saved['extensions']['actual_observations'][0]['sha256'],hashlib.sha256(raw.read_bytes()).hexdigest())
        self.assertFalse(saved['applied'])
        before=list(self.core.db.iterdump())
        with self.assertRaisesRegex(ValueError,'verification'):
            execute(self.io(),'complete',{'observed_state':self.observed(),'package_ref':f.r('missing'),
                'reason':'Declared fixture only','evidence_refs':[]})
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_compact_completion_binds_retained_state_without_loading_it_into_the_authored_input(self):
        observed=self.observed();before=list(self.core.db.iterdump())
        payload={'observed_state':observed,'package_ref':f.r('missing'),'reason':'Declared fixture only',
            'evidence_refs':[],'verification':{'usable':{'status':'PASS','rationale':'Explicit fixture only','evidence_refs':[]}}}
        with self.assertRaises(HostError):execute(self.io(),'complete',payload)
        self.assertEqual(before,list(self.core.db.iterdump()))
        self.core.begin(self.run_id,self.request())
        with self.assertRaisesRegex(ValueError,'observed state changed'):execute(self.io(),'complete',payload)

    def test_exact_result_file_is_checked_preserved_and_accepted_without_rewriting_its_values(self):
        op=self.core.begin(self.run_id,self.request());draft=self.payload(op,[f.evidence('file-result')])
        built=execute(self.io(),'build-result',draft);path=self.path/'explicit-result.json'
        raw=json.dumps(built,ensure_ascii=False).encode();path.write_bytes(raw)
        payload={'operation_ref':HostIO.reference(op),'observed_state':draft['observed_state'],
            'result_file':{'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}}
        before=list(self.core.db.iterdump());path.write_bytes(raw+b' ')
        rejected=self.invoke('finish',json.dumps(payload))
        self.assertEqual(rejected.returncode,2)
        self.assertIn('result file changed',rejected.stderr)
        self.assertEqual(before,list(self.core.db.iterdump()))
        path.write_bytes(raw)
        applied=self.invoke('finish',json.dumps(payload),'--receipt-only')
        self.assertEqual(applied.returncode,0,applied.stderr)
        record=Path(json.loads(applied.stdout)['record_dir'])
        self.assertEqual((record/'resolved-result.json').read_bytes(),raw)
        self.assertEqual(self.core.get(self.run_id,op['id'])['result']['outcome'],'UNKNOWN')
        self.assertEqual(json.loads((record/'input.json').read_text()),payload)
        both={**payload,'result':built}
        with self.assertRaisesRegex(ValueError,'unexpected'):
            execute(self.io(),'finish',both)

    def test_retained_discovery_ids_get_exact_diagnostics_without_automatic_filling(self):
        from test_learning import task
        doc=task('discovery-parent')
        doc['expansion']['discoveries']=[{'id':'retained-branch','content':'Earlier observed fixture branch',
            'source_locator':'Earlier synthetic observation','observation_kind':'measured','novelty':'Earlier fixture role',
            'parent_connection':'Fixture requirement','understanding_gap':'','assessment':'NONMATERIAL',
            'disposition':'EXCLUDE','target_refs':[],'rationale':'Explicit fixture scope exclusion','reopen_condition':'Fixture changes'}]
        self.put([f.evidence(),doc]);saved=self.core.get(self.run_id,doc['id'])
        plan=f.interpretation_plan(saved)
        op=self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',intent=plan))
        changed=HostIO.edit(saved)
        changed['expansion']['scope_rationale']='Earlier branch explicitly reassessed; no new fixture discovery'
        payload=self.payload(op,[changed]);payload['learning_results']=[{
            'task_ref':HostIO.reference(saved),'result_ref':HostIO.patch_ref(saved['id']),
            'answer_refs':[f.r('ev')],'understanding_change':'Explicit fixture comparison of retained branch',
            'discovery_ids':[],'upward_effects':['Fixture parent assessed'],'observations':['Actual fixture observation'],
            'prediction_difference':'Retaining an earlier item is distinct from adding a new item'}]
        before=list(self.core.db.iterdump());original=copy.deepcopy(payload)
        with self.assertRaises(f.ContractError) as caught:
            execute(self.io(),'build-result',payload)
        self.assertEqual(caught.exception.details,{'field':'learning_results[0].discovery_ids',
            'task_ref':f.r(saved['id'],saved['revision']+1),'expected_ids':['retained-branch'],
            'missing_ids':['retained-branch'],'unexpected_ids':[]})
        self.assertEqual(payload,original);self.assertEqual(before,list(self.core.db.iterdump()))
        failed=self.invoke('build-result',json.dumps(payload))
        self.assertEqual(failed.returncode,2)
        self.assertEqual(json.loads(failed.stderr)['detail']['missing_ids'],['retained-branch'])
        payload['learning_results'][0]['discovery_ids']=['other-branch']
        with self.assertRaises(f.ContractError) as unexpected:execute(self.io(),'build-result',payload)
        self.assertEqual(unexpected.exception.details['unexpected_ids'],['other-branch'])
        payload['learning_results'][0]['discovery_ids']=['retained-branch']
        applied=execute(self.io(),'result',payload)
        self.assertTrue(applied['applied'])
        self.assertEqual(self.core.get(self.run_id,op['id'])['result']['learning_results'][0]['discovery_ids'],['retained-branch'])
        self.assertIn('unresolved_items',input_contract('result')['required_fields'])

    def test_canonical_schema_bundle_is_complete_without_evidence_or_inference_defaults(self):
        from synframe_core.schema import schema_catalog
        contract=input_contract('result',['EvidenceRecord','LearningTask'])
        self.assertEqual(contract['entities'],{name:schema_catalog(name) for name in ['EvidenceRecord','LearningTask']})
        op=self.core.begin(self.run_id,self.request());before=list(self.core.db.iterdump())
        evidence=f.evidence('missing-kind');del evidence['observation_kind']
        with self.assertRaises(ValueError):execute(self.io(),'build-result',self.payload(op,[evidence]))
        task=HostIO.edit(self.core.get(self.run_id,'goal:goal-interpretation'))
        self.assertTrue(task['answer']['claims'])
        del task['answer']['claims'][0]['inference']
        with self.assertRaises(ValueError):execute(self.io(),'build-result',self.payload(op,[task]))
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_global_contract_bundle_with_run_does_not_send_a_run_flag_or_mutate_state(self):
        from synframe_host import read_contract
        entry=next(value for value in read_contract(f.SCRIPTS.parent)['files'] if value['name']=='SKILL.md')
        request={'ranges':[{'name':entry['name'],'sha256':entry['sha256'],'offset':0,'end':10}]}
        before=list(self.core.db.iterdump())
        result=self.io().call('read-contracts',request,max_bytes=4096)
        self.assertTrue(result['complete'])
        self.assertEqual(result['ranges'][0]['text'],(f.SCRIPTS.parent/'SKILL.md').read_text()[:10])
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_frame_schema_and_rejection_explain_the_existing_nonempty_question_link(self):
        from synframe_core.schema import schema_catalog
        field=schema_catalog('Frame')['structures']['Frame.information_requirements']
        self.assertIn('nonempty',field)
        self.assertIn('canonical LearningTask refs',field)
        op=self.core.begin(self.run_id,self.request())
        payload=self.payload(op,[f.frame('unlinked-frame',information_requirements=[])])
        before=list(self.core.db.iterdump());original=copy.deepcopy(payload)
        with self.assertRaisesRegex(f.ContractError,'later scope registration does not fill'):
            execute(self.io(),'build-result',payload)
        self.assertEqual(payload,original)
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_context_schema_matches_actual_wrappers_instead_of_flat_entity_assumptions(self):
        from test_learning import task as learning_task
        self.put([f.evidence(),learning_task('wrapper-question')])
        task=self.core.get(self.run_id,'wrapper-question')
        op=self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',intent=f.interpretation_plan(task)))
        before=list(self.core.db.iterdump())
        guide=self.io().call('schema',for_command='work-context')
        view=self.io().work_context(op,document_ids=['ev'])
        selected=view['selected_tasks'][0]
        self.assertEqual(set(selected),set(guide['output']['selected_tasks'][0]))
        self.assertNotIn('id',selected)
        self.assertEqual(selected['current']['id'],task['id'])
        self.assertTrue(selected['reference_current'])
        self.assertEqual(view['documents'][0]['id'],'ev')
        self.assertTrue(guide['output']['documents'].startswith('list:'))
        self.assertEqual(input_contract('context')['output_contract'],guide)
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_reuse_targets_expose_canonical_task_type_without_redirecting_consumers(self):
        from test_learning import task
        guide=input_contract('result',['LearningTask'])['entities']['LearningTask']
        self.assertIn('CREATE_TASK/PREREQUISITE/REUSE',guide['structures']['LearningTask.expansion.discoveries[]']['target_refs'])
        self.put([f.evidence()])
        doc=task('reuse-target')
        doc['expansion']['discoveries']=[{'id':'existing-answer','content':'Synthetic consumer reuse distinction',
            'source_locator':'Explicit fixture','observation_kind':'inference','novelty':'Fixture target type',
            'parent_connection':'Fixture need','understanding_gap':'','assessment':'MATERIAL',
            'disposition':'REUSE','target_refs':[f.r('goal')],
            'rationale':'Deliberately wrong consumer target in structural fixture','reopen_condition':''}]
        op=self.core.begin(self.run_id,self.request());payload=self.payload(op,[doc])
        before=list(self.core.db.iterdump());original=copy.deepcopy(payload)
        canonical=execute(self.io(),'build-result',payload)
        with self.assertRaisesRegex(HostError,'reuse-target/existing-answer.*goal:GoalSpec'):
            execute(self.io(),'finish',{'operation_ref':HostIO.reference(op),
                'observed_state':payload['observed_state'],'result':canonical})
        self.assertEqual(payload,original)
        self.assertEqual(before,list(self.core.db.iterdump()))


if __name__ == '__main__':
    unittest.main()
