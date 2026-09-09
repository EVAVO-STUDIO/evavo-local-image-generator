from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evavo_local_image_generator.provider_runner import ProviderError, ProviderRouter, _copy_verified, _generic_3d_brief


GENERIC_WORKER = r'''import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output-dir');p.add_argument('--name',default='artifact.bin');p.add_argument('--sha',action='store_true');p.add_argument('--bad-sha',action='store_true');a=p.parse_args()
out=pathlib.Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
artifact=out/a.name;artifact.write_bytes(b'EVAVO-PROVIDER-ARTIFACT')
receipt={'ok':True,'output':str(artifact.resolve())}
if a.sha:
 import hashlib
 receipt['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()
if a.bad_sha: receipt['sha256']='0'*64
print(json.dumps(receipt))
'''

ESCAPE_WORKER = r'''import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output-dir');a=p.parse_args()
artifact=pathlib.Path(a.output_dir).resolve().parents[2]/'evavo-escaped.bin';artifact.write_bytes(b'escape')
print(json.dumps({'ok':True,'output':str(artifact.resolve())}))
'''


class Fake3DHandler(BaseHTTPRequestHandler):
    compile_body = None

    def _json(self, status, body):
        payload=json.dumps(body).encode();self.send_response(status);self.send_header('content-type','application/json');self.send_header('content-length',str(len(payload)));self.end_headers();self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/api/v1/health':
            return self._json(200, {'ok':True,'service':'evavo-3d-agent-worker','executionEnabled':True})
        if self.path == '/api/v1/capabilities':
            return self._json(200, {'operations':['pipeline.full-candidate']})
        if self.path.startswith('/api/v1/jobs/'):
            job_id=self.path.rsplit('/',1)[-1]; body=self.__class__.compile_body
            workspace=Path(body['workspace']); artifact=workspace/'delivery'/'asset.optimised.glb';artifact.parent.mkdir(parents=True,exist_ok=True);artifact.write_bytes(b'glTF-fake-binary')
            sha=hashlib.sha256(artifact.read_bytes()).hexdigest()
            receipt={'executionStatus':'completed','jobId':job_id,'result':{'webDelivery':{'delivery':{'path':str(artifact.resolve()),'sha256':sha}}}}
            return self._json(200, {'state':{'status':'completed'},'receipt':receipt})
        return self._json(404, {'ok':False})

    def do_POST(self):
        length=int(self.headers.get('content-length','0')); body=json.loads(self.rfile.read(length) or b'{}')
        if self.path == '/api/v1/jobs/compile':
            self.__class__.compile_body=body
            compiled={'jobId':body['jobId'],'requestId':body['requestId'],'workspace':body['workspace'],'payload':body['payload'],'operation':body['operation'],'jobSha256':'a'*64}
            return self._json(200, compiled)
        if self.path == '/api/v1/jobs':
            return self._json(202, {'state':{'status':'queued'}})
        return self._json(404, {'ok':False})

    def log_message(self, fmt, *args):
        return


class ProviderRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.repo=self.base/'evavo-local-image-generator';self.repo.mkdir();self.state=self.repo/'state';self.results=self.repo/'results'
        self.worker=self.repo/'fake_worker.py';self.worker.write_text(GENERIC_WORKER,encoding='utf-8')
        self.router=ProviderRouter(self.repo,self.state,self.results)

    def tearDown(self): self.temp.cleanup()

    def test_generic_brief_has_stable_contract(self):
        brief=_generic_3d_brief('3d_1234567890', {'prompt':'A production ready wooden chair for a game scene'})
        self.assertEqual(brief['contractVersion'],'evavo_3d_asset_production_brief_v1');self.assertEqual(brief['input']['mode'],'text');self.assertIn('mask',brief['materials']['requiredChannels'])

    def test_audio_cli_success_and_path_confinement(self):
        argv=json.dumps([sys.executable,str(self.worker),'--request','{request_json}','--output-dir','{output_dir}','--name','audio.wav'])
        with patch.dict(os.environ, {'EVAVO_AUDIO_PROVIDER_ARGV':argv}, clear=False):
            result=asyncio.run(self.router.generate('audio','aud_1234567890',{'prompt':'hello'}))
        self.assertEqual(result.backend_mode,'audio-configured-cli');self.assertTrue(Path(result.paths[0]).is_file());self.assertTrue(Path(result.paths[0]).is_relative_to(self.results.resolve()))

    def test_generic_cli_verifies_supplied_sha256(self):
        argv=json.dumps([sys.executable,str(self.worker),'--request','{request_json}','--output-dir','{output_dir}','--name','audio.wav','--sha'])
        with patch.dict(os.environ, {'EVAVO_AUDIO_PROVIDER_ARGV':argv}, clear=False):
            result=asyncio.run(self.router.generate('audio','aud_1234567892',{'prompt':'hello'}))
        self.assertTrue(Path(result.paths[0]).is_file())
        self.assertRegex(str(result.receipt['sha256']), r'^[0-9a-f]{64}$')

    def test_generic_cli_rejects_receipt_sha256_mismatch(self):
        argv=json.dumps([sys.executable,str(self.worker),'--request','{request_json}','--output-dir','{output_dir}','--name','audio.wav','--bad-sha'])
        with patch.dict(os.environ, {'EVAVO_AUDIO_PROVIDER_ARGV':argv}, clear=False):
            with self.assertRaises(ProviderError) as context:
                asyncio.run(self.router.generate('audio','aud_1234567893',{'prompt':'hello'}))
        self.assertEqual(context.exception.code,'PROVIDER_OUTPUT_INVALID')

    def test_cli_escape_is_rejected(self):
        escape=self.repo/'escape.py';escape.write_text(ESCAPE_WORKER,encoding='utf-8')
        argv=json.dumps([sys.executable,str(escape),'--request','{request_json}','--output-dir','{output_dir}'])
        with patch.dict(os.environ, {'EVAVO_AUDIO_PROVIDER_ARGV':argv}, clear=False):
            with self.assertRaises(ProviderError) as context:
                asyncio.run(self.router.generate('audio','aud_1234567891',{'prompt':'hello'}))
        self.assertEqual(context.exception.code,'PROVIDER_OUTPUT_INVALID')

    def test_copy_verified_rejects_source_symlink(self):
        task_root=self.base/'task';task_root.mkdir();source=task_root/'real.bin';source.write_bytes(b'real')
        link=task_root/'link.bin'
        try: link.symlink_to(source)
        except (OSError,NotImplementedError) as exc: self.skipTest(f'symlinks unavailable: {exc}')
        with self.assertRaises(ProviderError) as context:
            _copy_verified(link,self.results/'copied.bin',admitted_root=task_root)
        self.assertEqual(context.exception.code,'PROVIDER_OUTPUT_INVALID')
        self.assertIn('symlink',str(context.exception).lower())

    def test_copy_verified_rejects_destination_symlink_without_touching_target(self):
        task_root=self.base/'task2';task_root.mkdir();source=task_root/'real.bin';source.write_bytes(b'real-provider-data')
        self.results.mkdir(parents=True,exist_ok=True);external=self.base/'external.bin';external.write_bytes(b'do-not-overwrite')
        destination=self.results/'copied.bin'
        try: destination.symlink_to(external)
        except (OSError,NotImplementedError) as exc: self.skipTest(f'symlinks unavailable: {exc}')
        with self.assertRaises(ProviderError) as context:
            _copy_verified(source,destination,admitted_root=task_root)
        self.assertEqual(context.exception.code,'PROVIDER_OUTPUT_INVALID')
        self.assertEqual(external.read_bytes(),b'do-not-overwrite')

    def test_video_override_uses_same_bounded_contract(self):
        argv=json.dumps([sys.executable,str(self.worker),'--request','{request_json}','--output-dir','{output_dir}','--name','video.mp4'])
        with patch.dict(os.environ, {'EVAVO_VIDEO_PROVIDER_ARGV':argv}, clear=False):
            result=asyncio.run(self.router.generate('video','vid_1234567890',{'prompt':'slow camera move'}))
        self.assertEqual(result.backend_mode,'video-configured-cli');self.assertTrue(Path(result.paths[0]).is_file())

    def test_services_prefer_canonical_comfyui_endpoint(self):
        env={
            'COMFYUI_ENDPOINT':'http://127.0.0.1:19001',
            'EVAVO_COMFYUI_ENDPOINT':'http://127.0.0.1:19002',
            'EVAVO_AUDIO_PROVIDER_ARGV':'',
            'EVAVO_VIDEO_PROVIDER_ARGV':'',
            'EVAVO_WAN21_MODEL_DIR':'',
            'EVAVO_3D_AGENT_EXECUTION_TOKEN':'',
            'EVAVO_3D_AGENT_WORKSPACE_ROOT':'',
        }
        with patch.dict(os.environ,env,clear=False):
            services=asyncio.run(self.router.services(comfyui_ready=True))
        self.assertEqual(services['image']['endpoint'],'http://127.0.0.1:19001')

    def test_3d_non_loopback_endpoint_is_rejected_before_network(self):
        env={'EVAVO_3D_ENDPOINT':'http://example.com:4314','EVAVO_3D_AGENT_EXECUTION_TOKEN':'x'*32,'EVAVO_3D_AGENT_WORKSPACE_ROOT':str(self.base/'3d-work')}
        with patch.dict(os.environ,env,clear=False):
            with self.assertRaises(ProviderError) as context:
                asyncio.run(self.router.generate('3d','3d_1234567891',{'prompt':'chair'}))
        self.assertEqual(context.exception.code,'PROVIDER_CONFIG_INVALID')

    def test_3d_worker_http_contract(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fake3DHandler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            env={'EVAVO_3D_ENDPOINT':f'http://127.0.0.1:{server.server_port}','EVAVO_3D_AGENT_EXECUTION_TOKEN':'x'*32,'EVAVO_3D_AGENT_WORKSPACE_ROOT':str(self.base/'3d-work')}
            with patch.dict(os.environ,env,clear=False):
                result=asyncio.run(self.router.generate('3d','3d_1234567890',{'prompt':'A production ready wooden chair for a game scene'}))
            self.assertEqual(result.backend_mode,'3d-studio-agent-worker');self.assertTrue(Path(result.paths[0]).is_file());self.assertEqual(Path(result.paths[0]).suffix,'.glb')
            self.assertEqual(Fake3DHandler.compile_body['operation'],'pipeline.full-candidate')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__ == '__main__': unittest.main(verbosity=2)
