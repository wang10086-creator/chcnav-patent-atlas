"""Isolated administrator authorization and full manual-monitor workflow tests.

All users, statuses and private data are temporary fixtures, never production.
"""
import base64
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from manual_monitor_admin import COOKIE, MAX_BODY, Server, Workbench, initialize

PASSWORD = 'ISOLATED_ONLY_long_test_password_2026'


class AdminServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='chcnav-admin-test-')
        self.data = Path(self.temp.name)
        initialize(self.data, 'fixture-manager', PASSWORD)
        self.work = Workbench(self.data)
        self.server = Server(('127.0.0.1', 0), self.work)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = self.server.origin
        self.sid, self.csrf = '', ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def call(self, method, path, value=None, headers=None, authenticated=True):
        h = {'Host': f'127.0.0.1:{self.server.server_port}'}
        if authenticated and self.sid:
            h['Cookie'] = f'{COOKIE}={self.sid}'
        body = None
        if method == 'POST':
            h.update({'Origin': self.origin, 'Content-Type': 'application/json'})
            if authenticated and self.csrf:
                h['X-CSRF-Token'] = self.csrf
            body = json.dumps(value or {}, ensure_ascii=False).encode('utf-8')
        h.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=25)
        connection.request(method, path, body, h)
        response = connection.getresponse()
        data = response.read()
        info = dict(response.getheaders())
        status = response.status
        connection.close()
        return status, json.loads(data) if info.get('Content-Type', '').startswith('application/json') else data, info

    def login(self):
        status, body, headers = self.call('POST', '/api/login', dict(username='fixture-manager', password=PASSWORD), authenticated=False)
        self.assertEqual(status, 200)
        self.sid = headers['Set-Cookie'].split(';', 1)[0].split('=', 1)[1]
        self.csrf = body['csrfToken']
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertEqual(body['user']['role'], 'administrator')

    def payload(self, status='隔离夹具状态 A', login='authenticated'):
        doc = json.loads(self.work.baseline.read_text())[0]
        query = 'ISOLATED ADMIN FIXTURE — NEVER A REAL INCOPAT SEARCH'
        text = ('publicationNumber,applicationNumber,title,applicants,legalStatus,legalEvent,eventDate\n'
                f'{doc["id"]},{doc["applicationNumber"]},隔离工作台夹具,上海华测导航技术股份有限公司,{status},隔离事件,2026-01-01\n')
        data = text.encode('utf-8')
        file_hash = hashlib.sha256(data).hexdigest()
        metadata = dict(searchQuery=query, timeFrom='2026-01-01', timeTo='2026-11-03',
                        executedAt='2026-11-03T17:08:19+08:00', sourceUrl='https://www-incopat-com-s-6.proxy.itic-sci.com/',
                        totalResults=1, resultCountBasis='publications', loginStatus=login,
                        exportComplete=True, coverageSchemaVersion=2, resultPageCount=1, resultPageSize=20,
                        expectedExportBatches=1, downloadedExportBatches=1,
                        exportBatches=[dict(range='1-1', recordCount=1, sha256=file_hash, searchQuery=query)])
        return dict(files=[dict(name='isolated.csv', contentBase64=base64.b64encode(data).decode())], metadata=metadata)

    def test_unauthenticated_and_frontend_flags_cannot_access_private_data(self):
        for path in ['/api/session', '/api/config', '/api/runs', '/administrator.json', '/static/../../administrator.json']:
            self.assertEqual(self.call('GET', path, headers={'Cookie': 'isAdmin=true; role=administrator'}, authenticated=False)[0], 401)
        self.assertEqual(self.call('POST', '/api/runs', self.payload(), authenticated=False)[0], 401)
        self.assertFalse(list((self.data / 'runs').iterdir()))

    def test_initialization_is_explicit_private_and_non_overwriting(self):
        with self.assertRaises(ValueError):
            initialize(self.data, 'fixture-manager', 'REPLACEMENT_PASSWORD_1234')
        with self.assertRaises(ValueError):
            initialize(ROOT / 'private-test-must-not-exist', 'manager', PASSWORD)
        self.assertFalse((ROOT / 'private-test-must-not-exist').exists())
        saved = (self.data / 'administrator.json').read_text()
        self.assertNotIn(PASSWORD, saved)
        (self.data / 'administrator.json').unlink()
        self.assertEqual(self.call('GET', '/api/session', authenticated=False)[0], 503)
        self.assertEqual(self.call('POST', '/api/login', dict(username='manager', password=PASSWORD), authenticated=False)[0], 503)

    def test_session_csrf_origin_host_logout_and_expiry(self):
        self.login()
        self.assertEqual(self.call('POST', '/api/runs', self.payload(), headers={'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.call('POST', '/api/runs', self.payload(), headers={'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.call('GET', '/api/config', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.call('GET', '/api/config', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.call('GET', '/api/config', headers={'Cookie': f'{COOKIE}=forged'})[0], 401)
        self.assertEqual(self.call('POST', '/api/logout')[0], 200)
        self.assertEqual(self.call('GET', '/api/config')[0], 401)
        self.login()
        self.work.sessions[self.sid]['expires'] = time.monotonic() - 1
        self.assertEqual(self.call('GET', '/api/config')[0], 401)

    def test_login_rate_limit_and_invalid_role(self):
        for _ in range(5):
            self.assertEqual(self.call('POST', '/api/login', dict(username='fixture-manager', password='wrong'), authenticated=False)[0], 401)
        self.assertEqual(self.call('POST', '/api/login', dict(username='fixture-manager', password=PASSWORD), authenticated=False)[0], 429)
        self.work.attempts.clear()
        path = self.data / 'administrator.json'
        identity = json.loads(path.read_text())
        identity['role'] = 'visitor'
        path.write_text(json.dumps(identity))
        self.assertEqual(self.call('POST', '/api/login', dict(username='fixture-manager', password=PASSWORD), authenticated=False)[0], 503)

    def test_manual_review_baseline_and_next_run_changes(self):
        self.login()
        status, run, _ = self.call('POST', '/api/runs', self.payload())
        self.assertEqual(status, 201)
        self.assertEqual(run['status'], 'review-required', run)
        self.assertEqual(run['report']['counts']['firstStatusObservations'], 1)
        self.assertEqual(run['report']['counts']['stateChanges'], 0)
        self.assertEqual(self.call('GET', '/api/runs/' + run['id'] + '/public-summary')[0], 403)
        review = dict(acknowledged=True, reviewNote='隔离测试：已逐项核对来源与覆盖，并非真实专利审核。')
        status, approved, _ = self.call('POST', '/api/runs/' + run['id'] + '/approve', review)
        self.assertEqual(status, 200, approved)
        self.assertEqual(approved['status'], 'approved')
        self.assertFalse(approved['published'])
        baseline_id = approved['baselineId']
        self.assertEqual(self.call('GET', '/api/baselines/' + baseline_id)[0], 200)
        self.assertEqual(self.call('POST', '/api/runs/' + run['id'] + '/approve', review)[0], 409)
        summary = self.call('GET', '/api/runs/' + run['id'] + '/public-summary')[1]
        self.assertNotIn('observations', summary)
        self.assertNotIn('reviewNote', summary)
        self.assertEqual(summary['publicationState'], 'approved-for-review-not-published')
        second = self.payload(status='隔离夹具状态 B')
        second['baselineId'] = baseline_id
        status, changed, _ = self.call('POST', '/api/runs', second)
        self.assertEqual(status, 201)
        self.assertEqual(changed['report']['counts']['stateChanges'], 1)
        self.assertEqual(changed['report']['counts']['firstStatusObservations'], 0)

    def test_failed_coverage_or_invalid_files_cannot_be_approved(self):
        self.login()
        payload = self.payload(login='expired')
        run = self.call('POST', '/api/runs', payload)[1]
        self.assertEqual(run['status'], 'failed')
        status = self.call('POST', '/api/runs/' + run['id'] + '/approve', dict(acknowledged=True, reviewNote='隔离测试尝试不能批准错误覆盖和失效登录。'))[0]
        self.assertEqual(status, 422)
        payload = self.payload()
        payload['files'][0]['name'] = '../../administrator.json'
        bad = self.call('POST', '/api/runs', payload)[1]
        self.assertEqual(bad['status'], 'failed')
        self.assertEqual(bad['report']['runState'], 'import-failed')
        self.assertEqual(self.call('POST', '/api/runs', self.payload(), headers={'Content-Length': str(MAX_BODY + 1)})[0], 413)


if __name__ == '__main__':
    unittest.main(verbosity=2)
