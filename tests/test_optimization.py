"""Lossless transport/read-only fixtures; no autonomous semantic quality claim."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_core as f
from synframe_host import HostIO, HostError
from synframe_core.files import file_sha256


class OptimizationAcceptance(unittest.TestCase):
    setUp=f.CoreAcceptance.setUp
    tearDown=f.CoreAcceptance.tearDown
    revision=f.CoreAcceptance.revision
    request=f.CoreAcceptance.request
    put=f.CoreAcceptance.put
    base=f.CoreAcceptance.base
    review=f.CoreAcceptance.review
    review_extensions=f.CoreAcceptance.review_extensions

    def test_explicit_schema_bundle_equals_individual_complete_results_and_is_read_only(self):
        io=HostIO(self.path,self.run_id);before=list(self.core.db.iterdump())
        names=('Frame','KnowledgeAsset','Capability','SolutionCandidate')
        bundle=io.schemas(*names)
        self.assertEqual(bundle,{name:io.call('schema',entity=name) for name in names})
        for values in [('Frame','Frame'),('Frame','Unknown')]:
            with self.assertRaises(HostError):io.schemas(*values)
        with self.assertRaises(ValueError):io.schemas()
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_compact_cli_preserves_all_json_values_and_rejection_codes(self):
        self.put([f.evidence(claim='한국어  \n  中文\tEnglish  ')])
        io=HostIO(self.path,self.run_id)
        base=[sys.executable,str(io.cli),'--state',str(self.path)]
        args=['list','--run',self.run_id]
        pretty=subprocess.run(base+args,text=True,capture_output=True)
        compact=subprocess.run(base+['--compact']+args,text=True,capture_output=True)
        self.assertEqual(pretty.returncode,compact.returncode)
        self.assertEqual(json.loads(pretty.stdout),json.loads(compact.stdout))
        self.assertLess(len(compact.stdout),len(pretty.stdout))
        self.assertEqual(next(d for d in json.loads(compact.stdout) if d['id']=='ev')['claim'],
                         '한국어  \n  中文\tEnglish  ')
        wrong=['schema','--entity','Unknown']
        pretty=subprocess.run(base+wrong,text=True,capture_output=True)
        compact=subprocess.run(base+['--compact']+wrong,text=True,capture_output=True)
        self.assertEqual((pretty.returncode,compact.returncode),(2,2))
        self.assertEqual(json.loads(pretty.stderr),json.loads(compact.stderr))

    def test_preservation_return_replaces_get_and_keeps_exact_receipts(self):
        io=HostIO(self.path,self.run_id)
        op=self.core.begin(self.run_id,self.request())
        files=[]
        for i,data in enumerate([b'',bytes(range(256))*8193]):
            path=self.path/('raw-'+str(i));path.write_bytes(data)
            files.append((path,'fixture-'+str(i)))
        saved=io.preserve_files(op,files)
        self.assertEqual(saved,io.call('get',id=op['id']))
        self.assertEqual([{k:r[k] for k in ('path','source','sha256')}
            for r in saved['extensions']['actual_observations']],
            [{'path':str(p.resolve()),'source':source,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p,source in files])
        with self.assertRaisesRegex(HostError,'revision conflict'):
            io.preserve_files(op,files)
        files[-1][0].write_bytes(b'changed')
        self.assertNotEqual(file_sha256(files[-1][0]),saved['extensions']['actual_observations'][-1]['sha256'])

    def test_streaming_hash_matches_all_boundaries_and_missing_file_errors(self):
        path=self.path/'binary'
        for size in [0,1,1023,1024,1048576,1048577]:
            data=(bytes(range(256))*((size+255)//256))[:size];path.write_bytes(data)
            self.assertEqual(file_sha256(path),hashlib.sha256(data).hexdigest())
        path.unlink()
        with self.assertRaises(FileNotFoundError):file_sha256(path)

    def test_review_and_gate_share_only_one_current_document_read(self):
        self.base();self.review();before=list(self.core.db.iterdump())
        with patch.object(self.core,'documents',wraps=self.core.documents) as reads:
            view=self.core.review_context(self.run_id,f.r('candidate'))
            self.assertEqual(reads.call_count,1)
        with patch.object(self.core,'documents',wraps=self.core.documents) as reads:
            gate=self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))
            self.assertEqual(reads.call_count,1)
        self.assertTrue(gate['passed']);self.assertFalse(view['structure']['errors'])
        self.assertFalse(self.core.db.in_transaction)
        self.assertEqual(before,list(self.core.db.iterdump()))

    def test_read_view_does_not_survive_changes_or_leak_mutable_results(self):
        self.base();self.review()
        view=self.core.review_context(self.run_id,f.r('candidate'))
        view['structure']['coverage'].clear()
        self.assertTrue(self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))['passed'])
        self.put([HostIO.edit(self.core.get(self.run_id,'ev'),claim='Actual changed fixture evidence')])
        gate=self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))
        self.assertFalse(gate['passed'])
        self.assertFalse(self.core.db.in_transaction)

    def test_read_view_keeps_historical_missing_and_stale_reference_errors(self):
        self.base();self.review()
        for pointer in [f.r('absent'),f.r('candidate',999)]:
            with self.assertRaises(f.ContractError) as plain:self.core.resolve(self.run_id,pointer)
            with self.core._read_view(self.run_id) as (_,resolve):
                with self.assertRaises(f.ContractError) as shared:resolve(pointer)
            self.assertEqual(str(plain.exception),str(shared.exception))
        with self.core.transaction():
            self.assertTrue(self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))['passed'])
            self.assertTrue(self.core.db.in_transaction)

    def test_read_query_uses_one_snapshot_during_another_connections_write(self):
        self.base();self.review();before=self.revision()
        request=self.request();other=f.Core(self.path)
        documents=self.core.documents;written=[]
        def read_and_write(run_id):
            result=documents(run_id)
            if not written:
                written.append(True)
                op=other.begin(run_id,request)
                value=f.output(op,[f.evidence('concurrent')],core=other)
                other.apply(run_id,op['id'],other.prepare(run_id,op['id'],value))
            return result
        try:
            with patch.object(self.core,'documents',side_effect=read_and_write):
                view=self.core.review_context(self.run_id,f.r('candidate'))
            self.assertEqual(view['observed_revision'],before)
            self.assertGreater(self.revision(),before)
            self.assertFalse(self.core.db.in_transaction)
            self.assertTrue(self.core.commit_gate(self.run_id,f.r('candidate'),f.r('review'))['passed'])
        finally:other.close()

    def test_installer_preserves_previous_installation_outside_skill_discovery(self):
        spec=importlib.util.spec_from_file_location('synframe_installer',f.ROOT/'tools/install.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        destination=self.path/'install/skills/synframe'
        first=installer.install(destination)
        self.assertIsNone(first['backup'])
        (destination/'custom.txt').write_text('Preserved user customization')
        second=installer.install(destination)
        backup=Path(second['backup'])
        self.assertEqual((backup/'custom.txt').read_text(),'Preserved user customization')
        self.assertNotIn(destination.parent,backup.parents)
        self.assertEqual(first['sha256'],second['sha256'])
        foreign=self.path/'foreign';foreign.mkdir();(foreign/'keep.txt').write_text('Keep')
        with self.assertRaises(ValueError):installer.install(foreign)
        self.assertEqual((foreign/'keep.txt').read_text(),'Keep')


if __name__=='__main__':unittest.main()
