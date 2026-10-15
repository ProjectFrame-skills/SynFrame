"""Authoring/retention fixtures, not host judgment or independent quality proof."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_core as f
from synframe_host import HostIO, HostError, read_contract
from synframe_core.schema import ContractError, validate_completion


class ErrorRemovalAcceptance(unittest.TestCase):
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

    def prepared(self):
        self.base(); self.review(); self.commit(); self.package()
        return HostIO(self.path,self.run_id)

    def checks(self):
        return {'usable':{'status':'PASS','evidence_refs':[f.r('ev')],
            'rationale':'Explicit synthetic fixture observation; not autonomous judgment'}}

    def test_completion_shape_matches_command_catalog_and_completes_without_format_retry(self):
        io = self.prepared(); context = io.work_context()
        contract = io.call('schema',for_command='transition')
        self.assertEqual(set(contract['verification_check']),set(self.checks()['usable']))
        result = io.complete(context,package_ref=f.r('package'),reason='Declared fixture verified',
            evidence_refs=[f.r('ev')],verification=self.checks())
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(io.call('resume')['status']['run']['state'],'COMPLETED')

    def test_four_observed_completion_shape_mistakes_have_exact_diagnostics_and_no_state_calls(self):
        io = self.prepared(); context = io.work_context(); before = list(self.core.db.iterdump())
        malformed = [{'success_criteria':self.checks()}, {'criteria':self.checks()},
            {'usable':{'status':'PASS','evidence_refs':[f.r('ev')],'observations':'fixture'}},
            {'usable':{'status':'PASS','evidence_refs':[f.r('ev')],'observation':'fixture'}}]
        with patch.object(io,'call',wraps=io.call) as calls:
            for value in malformed:
                with self.assertRaises(ContractError) as caught:
                    io.complete(context,package_ref=f.r('package'),reason='Fixture',evidence_refs=[],verification=value)
                self.assertIn('path',caught.exception.details)
                self.assertTrue('expected' in caught.exception.details or 'expected_keys' in caught.exception.details)
            calls.assert_not_called()
        self.assertEqual(before,list(self.core.db.iterdump()))
        with self.assertRaises(HostError) as caught:
            io.call('transition',{'target':'COMPLETED','reason':'Fixture','package_ref':f.r('package'),
                'verification':malformed[-1]},expected=context['revision'])
        self.assertEqual(caught.exception.detail['path'],'verification.usable')
        self.assertEqual(caught.exception.detail['expected_keys'],['evidence_refs','rationale','status'])
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_completion_never_generates_pass_or_refreshes_stale_context(self):
        io = self.prepared(); context = io.work_context()
        for status in ('FAIL','UNKNOWN'):
            checks = self.checks(); checks['usable']['status']=status
            with self.assertRaisesRegex(HostError,'unverified success criterion'):
                io.complete(context,package_ref=f.r('package'),reason='Fixture',evidence_refs=[],verification=checks)
        self.put([f.evidence('new-observation')]); before = list(self.core.db.iterdump())
        with self.assertRaisesRegex(HostError,'revision conflict'):
            io.complete(context,package_ref=f.r('package'),reason='Fixture',evidence_refs=[],verification=self.checks())
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_completion_keeps_pending_effects_and_minor_uncertainty_grounds_required(self):
        io = self.prepared()
        self.put([HostIO.edit(self.core.get(self.run_id,'package'),uncertainties=[
            {'description':'Unassessed fixture uncertainty','important':False}])])
        with self.assertRaisesRegex(HostError,'minor package uncertainty'):
            io.complete(io.work_context(),package_ref=f.r('package',2),reason='Fixture',evidence_refs=[],verification=self.checks())
        self.core.begin(self.run_id,self.request('EXECUTE'))
        with self.assertRaisesRegex(HostError,'pending external effects'):
            io.complete(io.work_context(),package_ref=f.r('package',2),reason='Fixture',evidence_refs=[],verification=self.checks())

    def test_actual_returned_review_reference_is_used_but_old_judgment_stays_stale(self):
        self.base(); self.review(); io = HostIO(self.path,self.run_id)
        old = self.core.get(self.run_id,'review')
        op = self.core.begin(self.run_id,self.request('REVIEW_SOLUTION'))
        result = io.build_result(op,[io.edit(old)],result_ids=['review'],preserved_refs=[],
            evidence_refs=[f.r('ev')],unresolved_items=[],
            observed_effects=['Declared fixture review was serialized again without content change'],
            next_decision_inputs=['Compare actual returned review reference against Gate'],
            outcome='SUCCEEDED',learning_results=[],propagation_resolutions=[],path_assessments=[])
        applied = io.finish(op,result)
        current = io.result_ref(applied,'review')
        self.assertEqual(current,f.r('review',2))
        self.assertTrue(io.gate(f.r('candidate'),current)['passed'])
        with self.assertRaisesRegex(HostError,'stale reference'):
            io.gate(f.r('candidate'),io.reference(old))
        self.assertEqual(old,self.core.get(self.run_id,'review',old['revision']))
        with self.assertRaises(ValueError):io.result_ref(applied,'absent')

    def test_review_context_exposes_same_structural_errors_as_gate_before_authoring(self):
        self.put([f.evidence(),f.capability(),f.asset(inputs=[{'name':'source','type':'url'}]),f.link(),f.candidate()])
        io = HostIO(self.path,self.run_id); context = io.review_context(f.r('candidate'))
        self.assertIn('unbound input asset.source',context['structure']['io_errors'])
        self.assertNotIn('checks',context)
        self.review(); gate = self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))
        self.assertTrue(set(context['structure']['errors']) <= set(gate['errors']))

    def test_wrong_package_validation_type_reports_actual_and_required_types(self):
        io = self.prepared(); package = io.edit(self.core.get(self.run_id,'package'),validation_refs=[f.r('review')])
        with self.assertRaises(ContractError) as caught:self.put([package])
        self.assertEqual(caught.exception.details,{'path':'package.validation_refs[0]',
            'expected_type':'EvidenceRecord','actual_type':'ReviewRecord'})
        # put records an intent; rejected apply must not update the package.
        self.assertEqual(self.core.get(self.run_id,'package')['revision'],1)

    def test_explicit_current_context_retention_skips_only_matching_complete_ranges(self):
        root = self.path/'contract-source';root.mkdir();(root/'references').mkdir()
        (root/'SKILL.md').write_text('필수 상세 계약.\n'*5000)
        chunks=[read_contract(root,'SKILL.md',offset,6000) for offset in range(0,24000,6000)]
        receipts=[{k:c[k] for k in ('name','sha256','offset','end','chunk_sha256')} for c in chunks]
        retained={'retained_in_current_context':True,'ranges':receipts}
        self.assertEqual(sum(len(c['text']) for c in chunks),24000)
        reused=[read_contract(root,'SKILL.md',offset,6000,retained=retained) for offset in range(0,24000,6000)]
        self.assertEqual(sum(len(c['text']) for c in reused),0)
        self.assertTrue(all(c['reused_retained'] for c in reused))
        self.assertEqual(read_contract(root,'SKILL.md',24000,6000,retained=retained)['text'],
                         (root/'SKILL.md').read_text()[24000:30000])
        self.assertEqual(len(read_contract(root,'SKILL.md',0,6000)['text']),6000)
        lost={**retained,'retained_in_current_context':False}
        with self.assertRaises(ValueError):read_contract(root,'SKILL.md',0,6000,retained=lost)
        bad=copy.deepcopy(retained);bad['ranges'][0]['chunk_sha256']='0'*64
        with self.assertRaises(ValueError):read_contract(root,'SKILL.md',0,6000,retained=bad)
        (root/'SKILL.md').write_text('변경된 계약.\n'*5000)
        self.assertEqual(len(read_contract(root,'SKILL.md',0,6000,retained=retained)['text']),6000)

    def test_retention_cli_is_read_only_and_missing_retention_delivers_full_text(self):
        io = HostIO(self.path,self.run_id); before=list(self.core.db.iterdump())
        first=io.call('read-contract',name='references/decision-loop.md',offset=0,limit=6000)
        receipt={k:first[k] for k in ('name','sha256','offset','end','chunk_sha256')}
        path=self.path/'retained.json';path.write_text(json.dumps({'retained_in_current_context':True,'ranges':[receipt]}))
        second=io.call('read-contract',name=first['name'],offset=0,limit=6000,retained=path)
        self.assertEqual(second['text'],'');self.assertTrue(second['reused_retained'])
        self.assertEqual(io.call('read-contract',name=first['name'],offset=0,limit=6000)['text'],first['text'])
        self.assertEqual(before,list(self.core.db.iterdump()))


if __name__=='__main__':unittest.main()
