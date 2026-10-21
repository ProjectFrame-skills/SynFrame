"""Delivery/application boundaries, never independent semantic quality proof."""
import copy
import hashlib
import json
import unittest
from unittest import mock
from pathlib import Path
from html.parser import HTMLParser

import test_core as fixtures
from test_learning import task,dep
from synframe_core.learning import basis
from synframe_core.schema import PACKAGE_FIELDS,schema_catalog
from synframe_host import HostIO,read_contract


class WorkLoopIOAcceptance(unittest.TestCase):
    setUp=fixtures.CoreAcceptance.setUp
    tearDown=fixtures.CoreAcceptance.tearDown
    request=fixtures.CoreAcceptance.request
    put=fixtures.CoreAcceptance.put
    revision=fixtures.CoreAcceptance.revision
    base=fixtures.CoreAcceptance.base
    review=fixtures.CoreAcceptance.review
    review_extensions=fixtures.CoreAcceptance.review_extensions
    commit=fixtures.CoreAcceptance.commit
    package=fixtures.CoreAcceptance.package
    completion=fixtures.CoreAcceptance.completion

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

    def test_requirements_context_exposes_missing_derivation_before_any_candidate(self):
        before=self.stored();packet=HostIO(self.path,self.run_id).work_context()
        context=packet['requirements_context']
        self.assertEqual(context['missing_capability_criterion_ids'],['usable'])
        self.assertEqual(context['criteria'][0]['source_facets'][0]['source_quote'],'implement through skills')
        self.assertFalse(context['capabilities'])
        # The operating/interpretation tasks are visible, but do not fill a
        # missing domain capability or silently create/answer a new question.
        self.assertTrue(context['learning_tasks'])
        self.assertIn('no stored committed candidate/review',packet['return_boundary']['adoption_errors'])
        self.assertEqual(self.stored(),before)

    def test_requirements_context_keeps_abilities_evidence_consumers_and_unanswered_quality(self):
        quality=task('quality');tool=task('tool',True)
        quality['dependency_refs']=[dep('tool')]
        cap=fixtures.capability();cap['extensions']['questions']=[fixtures.r('quality')]
        self.put([fixtures.evidence(),tool,quality,cap,
                  fixtures.link('quality-consumer',[fixtures.r('quality')],'cap','AFFECTS')])
        before=self.stored();context=self.core.work_context(self.run_id)['requirements_context']
        actual={d['id']:d for d in context['learning_tasks']}
        self.assertEqual(actual['quality']['answer_requirements'],quality['answer_requirements'])
        self.assertEqual(actual['quality']['understanding']['status'],'UNASSESSED')
        self.assertEqual(actual['tool']['understanding']['status'],'SUFFICIENT')
        self.assertEqual(context['question_links'][0]['declared_ref'],fixtures.r('quality'))
        self.assertTrue(context['question_links'][0]['reference_current'])
        self.assertTrue(any(c['source']['declared_ref']==fixtures.r('quality') and
                            c['target_ref']==fixtures.r('cap') for c in context['consumers']))
        self.assertTrue(any(c['source']['declared_ref']==fixtures.r('tool') and
                            c['target_ref']==fixtures.r('quality') for c in context['consumers']))
        self.assertEqual(context['evidence'][0]['id'],'ev')
        self.assertEqual(self.stored(),before)
        # Declaration coverage is not a semantic assertion that this generic
        # capability/fixture actually provides the user's intended quality.
        self.assertEqual(context['missing_capability_criterion_ids'],[])
        self.assertNotIn('passed',context)

    def test_requirements_projection_never_rebinds_old_question_reference(self):
        from synframe_core.deliberation import requirements_context
        self.put([fixtures.evidence(),task('quality')])
        documents=self.core.documents(self.run_id)
        cap=fixtures.capability();cap.update(revision=1,validity_status='VALID')
        cap['extensions']['questions']=[fixtures.r('quality',99)]
        context=requirements_context(self.core.get(self.run_id,'goal'),[*documents,cap])
        binding=context['question_links'][0]
        self.assertEqual(binding['declared_ref'],fixtures.r('quality',99))
        self.assertEqual(binding['current_ref'],fixtures.r('quality'))
        self.assertFalse(binding['reference_current'])
        cap['extensions']['questions']=[fixtures.r('missing')]
        context=requirements_context(self.core.get(self.run_id,'goal'),[*documents,cap])
        self.assertIsNone(context['question_links'][0]['current_ref'])

    def test_final_return_rejects_active_without_marking_work_done(self):
        io=HostIO(self.path,self.run_id);context=io.work_context();before=self.stored()
        with self.assertRaisesRegex(ValueError,'continue available required work'):
            io.return_result(context,text='Premature final recommendation')
        self.assertEqual(self.stored(),before)

    def test_final_return_uses_actual_current_state_not_a_forged_or_stale_context(self):
        self.put([fixtures.evidence(),task('unfinished')])
        io=HostIO(self.path,self.run_id);old=io.work_context()
        self.core.transition(self.run_id,'PARTIAL',self.revision(),'Declared fixture resource interruption')
        before=self.stored()
        with self.assertRaisesRegex(ValueError,'exact assessed current'):
            io.return_result(old,text='Old observed state')
        current=io.work_context();forged=copy.deepcopy(current);forged['run_ref']['id']='another-run'
        with self.assertRaisesRegex(ValueError,'exact assessed current'):
            io.return_result(forged,text='Wrong execution')
        limited=io.return_result(current,text='Explicit limited result; unanswered work remains.')
        self.assertEqual(limited['state'],'PARTIAL')
        self.assertTrue(io.work_context()['unfinished_learning'])
        self.assertEqual(self.stored(),before)

    def test_final_return_keeps_completed_adoption_gate_and_explicit_text(self):
        self.base();self.review();self.commit();self.package();self.completion()
        io=HostIO(self.path,self.run_id);context=io.work_context();before=self.stored()
        self.assertFalse(context['return_boundary']['adoption_errors'])
        self.assertEqual(context['requirements_context'],io.review_context(fixtures.r('candidate'))['requirements_context'])
        text='Exact explicitly authored result\nwith its scope.'
        result=io.return_result(context,text=text)
        self.assertEqual(result['text'],text)
        self.assertEqual(result['result_package_ref'],fixtures.r('package'))
        self.assertEqual(self.stored(),before)

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
        def context():
            before=self.stored();packet=io.work_context()
            self.assertEqual(self.stored(),before)  # No state, K, DDC or Review generated by the count.
            self.assertEqual(packet['state_digest'],self.core.observe(self.run_id)['state_digest'])
            self.assertEqual(packet['pending_propagation_count'],
                sum(o['status']=='PENDING' for o in packet['propagation_obligations']))
            return packet
        self.assertEqual(context()['pending_propagation_count'],0)
        for identity in ('child','parent'):
            old=self.core.get(self.run_id,identity)
            plan={'task_ref':io.reference(old),'parent_role':'Declared fixture prerequisite',
                'gap':'Declared open required ability','next_observation':{'target':identity,'source':'Synthetic observation',
                    'locator':'fixture receipt','information':'Declared condition','decision_effect':'Required fixture consumer'},
                'requirement_ids':['ability'],'known_evidence_refs':[fixtures.r('ev')],
                'judgment_target':{'target_ref':io.reference(old),'item_id':None,'decision':'Declared fixture ability',
                    'consumer_refs':[fixtures.r('parent') if identity=='child' else fixtures.r('candidate')],
                    'scope':'Synthetic boundary check'},
                'sufficient_when':'Actual fixture ability and dependency recorded','failure_alternative':'Keep open'}
            op=self.core.begin(self.run_id,self.request('DEEPEN_KNOWLEDGE',{'learning_task_refs':[io.reference(old)],'learning_plan':[plan]}))
            closed=task(identity,True)
            if identity=='parent':closed['dependency_refs']=[dep('child',2)]
            closed['closure_assessment']['basis']=basis(closed)
            changes=[closed]
            if identity=='parent':changes.append(fixtures.candidate(comparison_rationale='Declared child result consumed through parent'))
            resolutions=[{'id':o['id'],'assessment':'REVISE','evidence_refs':[fixtures.r('ev')],
                'rationale':'Declared child effect consumed by updated parent','result_refs':[fixtures.r('parent',2)],'remaining_work':[]}
                for o in context()['propagation_obligations'] if o['status']=='PENDING' and o['target_ref']['id']=='parent']
            learning=[{'task_ref':io.reference(old),'result_ref':fixtures.r(identity,2),'answer_refs':[fixtures.r('ev')],
                'understanding_change':'Declared sufficient fixture ability','discovery_ids':[],
                'upward_effects':['Declared actual consumer update'],'observations':['Fixture condition inspected'],
                'prediction_difference':'Declared fixture only'}]
            result=self.build(io,op,changes,learning_results=learning,propagation_resolutions=resolutions)
            io.finish(op,result)
            packet=context()
            self.assertEqual(packet['pending_propagation_count'],1)
            pending=[o for o in packet['propagation_obligations'] if o['status']=='PENDING']
            self.assertEqual(pending[0]['target_ref']['id'],'parent' if identity=='child' else 'candidate')
        self.assertFalse(packet['unfinished_learning'])
        self.assertEqual(packet['candidates'][0]['candidate_ref'],fixtures.r('candidate',2))
        self.assertIn('consumed through parent',packet['candidates'][0]['comparison_rationale'])
        self.assertFalse(packet['pending_operations'])
        self.assertFalse([o for o in packet['propagation_obligations'] if o['status']=='PENDING' and o['target_ref']['id']=='parent'])
        # Candidate content already changed; its explicit saved consumption
        # assessment still resolves the remaining parent→candidate obligation.
        current=packet['candidates'][0]['candidate_ref']
        op=self.core.begin(self.run_id,self.request('SIMPLIFY',{'candidate_ref':current}))
        resolutions=[{'id':o['id'],'assessment':'MAINTAIN','evidence_refs':[fixtures.r('ev')],
            'rationale':'Declared current candidate comparison consumes this exact parent result',
            'result_refs':[current],'remaining_work':[]} for o in pending]
        io.finish(op,self.build(io,op,[],preserved_refs=[current],propagation_resolutions=resolutions))
        resolved=context()
        self.assertEqual(resolved['pending_propagation_count'],0)
        self.assertTrue(all(next(o for o in resolved['propagation_obligations'] if o['id']==item['id'])['status']=='RESOLVED'
            for item in pending))

    def test_bad_observation_shapes_fail_before_any_state_write(self):
        io=HostIO(self.path,self.run_id);op=self.core.begin(self.run_id,self.request());before=self.stored()
        for files in ([{'path':'absent','label':'missing source'}],['not a pair'],[('absent','')]):
            with self.assertRaises(ValueError):io.preserve_files(op,files,expected_revision=self.revision())
        self.assertEqual(self.stored(),before)

    def test_structured_input_keyword_is_rejected_before_subprocess_without_state_change(self):
        io=HostIO(self.path,self.run_id);before=self.stored()
        for value in ({'target':'PARTIAL','reason':'Explicit fixture'}, [], 1):
            with self.subTest(value_type=type(value).__name__), mock.patch('synframe_host.subprocess.run') as process:
                with self.assertRaisesRegex(ValueError,'pass structured JSON as payload='):
                    io.call('transition',expected=self.revision(),input=value)
                process.assert_not_called()
        with mock.patch('synframe_host.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError,'not both'):
                io.call('learning-basis',task(),input='different.json')
            process.assert_not_called()
        self.assertEqual(self.stored(),before)

    def test_explicit_payload_and_file_input_keep_existing_readonly_behavior(self):
        io=HostIO(self.path,self.run_id);document=task();before=self.stored()
        path=Path(self.temp.name)/'explicit-input.json';path.write_text(json.dumps(document))
        expected=io.call('learning-basis',document)
        self.assertEqual(expected['basis'],basis(document))
        self.assertEqual(io.call('learning-basis',payload=document),expected)
        self.assertEqual(io.call('learning-basis',input=path),expected)
        self.assertEqual(self.stored(),before)

    def test_package_renderer_preserves_all_json_values_escapes_html_and_never_applies_state(self):
        contents={key:{'text':'긴 원문\n</pre><script>bad()</script> & "quote" 😀',
            'values':[None,True,False,0,1.5,'null',[],{}, {'nested':'<value>'}]}
            for key in sorted(PACKAGE_FIELDS)}
        before=self.stored();folder=Path(self.temp.name)/'outputs'
        receipt=HostIO.write_package(contents,path=folder/'package.json',format='json',source='Explicit host-authored fixture')
        self.assertEqual(json.loads(Path(receipt['path']).read_text()),contents)
        self.assertEqual(receipt['sha256'],hashlib.sha256(Path(receipt['path']).read_bytes()).hexdigest())
        html_receipt=HostIO.write_package(contents,path=folder/'package.html',format='html',source='Explicit same fixture')
        html=Path(html_receipt['path']).read_text()
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<ol>',html);self.assertIn('<ul>',html)

        class Reader(HTMLParser):
            def __init__(self):
                super().__init__();self.root=[];self.stack=[]
            def handle_starttag(self,tag,attrs):
                if tag in {'dl','dt','dd','ul','li','pre'}:
                    node=[tag,dict(attrs),[]]
                    (self.stack[-1][2] if self.stack else self.root).append(node)
                    self.stack.append(node)
            def handle_endtag(self,tag):
                if tag in {'dl','dt','dd','ul','li','pre'}:
                    assert self.stack[-1][0]==tag
                    self.stack.pop()
            def handle_data(self,value):
                if self.stack:self.stack[-1][2].append(value)
        def decode(node):
            tag,attrs,children=node
            if tag=='dl':return {''.join(children[i][2]):decode(children[i+1][2][0]) for i in range(0,len(children),2)}
            if tag=='ul':return [decode(item[2][0]) for item in children]
            value=''.join(children)
            return value if attrs['data-json-type']=='string' else json.loads(value)
        reader=Reader();reader.feed(html);reader.close()
        self.assertFalse(reader.stack);self.assertEqual(decode(reader.root[0]),contents)
        self.assertEqual(self.stored(),before)
        with self.assertRaises(FileExistsError):
            HostIO.write_package(contents,path=folder/'package.html',format='html',source='Do not overwrite')
        self.assertEqual(Path(html_receipt['path']).read_text(),html)

    def test_package_renderer_rejects_incomplete_non_json_and_implicit_inputs_before_creating_artifact(self):
        path=Path(self.temp.name)/'rejected-output'
        contents={key:None for key in PACKAGE_FIELDS}
        bad=[({},'html','Explicit source'),(contents,'markdown','Explicit source'),
            (contents,'json',''),({**contents,'Goal':float('nan')},'json','Explicit source'),
            ({**contents,'Goal':{1:'nonstring key'}},'html','Explicit source'),
            ({**contents,'Goal':('tuple',)},'html','Explicit source')]
        for value,format,source in bad:
            with self.subTest(format=format),self.assertRaises(ValueError):
                HostIO.write_package(value,path=path,format=format,source=source)
            self.assertFalse(path.exists())
        self.assertIn('receipt.path',schema_catalog('EvidenceRecord')['structures']['EvidenceRecord.source'])
        package_shape=schema_catalog('SolutionPackage')['structures']
        self.assertEqual(set(package_shape['SolutionPackage.contents']),PACKAGE_FIELDS)
        self.assertNotIn('SolutionPackage.contents.artifact_rendering',package_shape)

if __name__=='__main__':unittest.main()
