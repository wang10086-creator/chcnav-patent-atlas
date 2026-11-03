"""Independent administrator-boundary tests. All identities/data are temporary.

Run: python3 scripts/monitor_tests/test_manual_admin_security.py
No production administrator, private export, server on port 8766, or Git remote is used.
"""
import base64
from contextlib import contextmanager
import hashlib
import http.client
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import threading
import time
import unittest
import warnings
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(Path(__file__).resolve().parent)]
import manual_monitor_admin as admin
import test_native_incopat_xlsx as fixtures

CHECKS = []
USERNAME = 'isolated-security-manager'
PASSWORD = 'ISOLATED_TEST_ONLY_security_longpass_2026'
SOURCE_SHA = hashlib.sha256(Path(admin.__file__).read_bytes()).hexdigest()


def verify(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def request(server, method, path, payload=None, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    combined = {'Content-Type': 'application/json'} if body is not None else {}
    combined.update(headers or {})
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=30)
    connection.request(method, path, body=body, headers=combined)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


@contextmanager
def isolated_server(initialized=True):
    with tempfile.TemporaryDirectory(prefix='chcnav-independent-admin-security-') as temporary:
        directory = Path(temporary)
        work = admin.Workbench(directory / 'private')
        if initialized:
            admin.initialize(work.directory, USERNAME, PASSWORD)
        server = admin.Server(('127.0.0.1', 0), work)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield directory, work, server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def login(server):
    status, headers, body = request(server, 'POST', '/api/login',
        {'username': USERNAME, 'password': PASSWORD}, {'Origin': server.origin})
    verify('valid backend administrator login', status == 200)
    session = json.loads(body)
    cookie = headers['Set-Cookie'].split(';', 1)[0]
    return session, cookie, headers, body


class AdministratorSecurityTests(unittest.TestCase):
    def test_full_permission_and_review_boundary(self):
        with isolated_server(initialized=False) as (directory, work, server):
            origin = server.origin
            verify('uninitialized session fails closed', request(server, 'GET', '/api/session')[0] == 503)
            verify('uninitialized login fails closed', request(server, 'POST', '/api/login',
                {'username': USERNAME, 'password': PASSWORD}, {'Origin': origin})[0] == 503)
            admin.initialize(work.directory, USERNAME, PASSWORD)
            if sys.platform != 'win32':
                verify('private directory mode 0700', stat.S_IMODE(work.directory.stat().st_mode) == 0o700)
                verify('private identity mode 0600', stat.S_IMODE((work.directory / 'administrator.json').stat().st_mode) == 0o600)
            verify('identity contains no plaintext password', PASSWORD not in (work.directory / 'administrator.json').read_text())
            with self.assertRaises(ValueError):
                admin.initialize(work.directory, 'replacement', 'another-isolated-long-password')
            CHECKS.append('second initialization cannot reset identity')
            cases = [
                ('anonymous private read denied', 'GET', '/api/runs', None, {}, 401),
                ('anonymous mutation denied', 'POST', '/api/runs', {}, {'Origin': origin}, 401),
                ('private identity not served', 'GET', '/administrator.json', None, {}, 401),
                ('static path traversal denied', 'GET', '/static/../../administrator.json', None, {}, 401),
                ('wrong Host denied', 'GET', '/', None, {'Host': 'evil.invalid'}, 403),
                ('foreign Origin private read denied', 'GET', '/api/session', None, {'Origin': 'https://evil.invalid'}, 403),
                ('login without Origin denied', 'POST', '/api/login', {'username': USERNAME, 'password': PASSWORD}, {}, 403),
                ('cross-origin preflight denied', 'OPTIONS', '/api/runs', None, {'Origin': 'https://evil.invalid'}, 403),
                ('public top-level navigation only opens login shell', 'GET', '/', None,
                 {'Origin': 'https://public.invalid', 'Sec-Fetch-Site': 'cross-site',
                  'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}, 200),
                ('navigation exception never opens private API', 'GET', '/api/runs', None,
                 {'Origin': 'https://public.invalid', 'Sec-Fetch-Site': 'cross-site',
                  'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}, 403),
            ]
            for label, method, path, payload, headers, expected in cases:
                verify(label, request(server, method, path, payload, headers)[0] == expected)
            session, cookie, headers, body = login(server)
            auth = {'Origin': origin, 'Cookie': cookie, 'X-CSRF-Token': session['csrfToken']}
            verify('session cookie HttpOnly', 'HttpOnly' in headers['Set-Cookie'])
            verify('session cookie SameSite Strict', 'SameSite=Strict' in headers['Set-Cookie'])
            verify('session response excludes private identity hashes', not any(
                key in body for key in (b'passwordHash', b'identityDigest', b'salt')))
            cases = [
                ('valid session recognized', 'GET', '/api/session', None, {'Cookie': cookie}, 200),
                ('forged session rejected', 'GET', '/api/session', None, {'Cookie': admin.COOKIE + '=forged'}, 401),
                ('missing CSRF rejected', 'POST', '/api/runs', {}, {'Origin': origin, 'Cookie': cookie}, 403),
                ('incorrect CSRF rejected', 'POST', '/api/runs', {}, {'Origin': origin, 'Cookie': cookie, 'X-CSRF-Token': 'invalid'}, 403),
                ('mutation without Origin rejected', 'POST', '/api/runs', {}, {'Cookie': cookie, 'X-CSRF-Token': session['csrfToken']}, 403),
                ('mutation foreign Origin rejected', 'POST', '/api/runs', {}, {'Origin': 'https://evil.invalid', 'Cookie': cookie, 'X-CSRF-Token': session['csrfToken']}, 403),
            ]
            for label, method, path, payload, request_headers, expected in cases:
                verify(label, request(server, method, path, payload, request_headers)[0] == expected)
            for duplicate in ('Host', 'Origin', 'Content-Length', 'Cookie', 'X-CSRF-Token'):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                connection.putrequest('POST', '/api/login', skip_host=True)
                connection.putheader('Host', origin[7:])
                connection.putheader('Origin', origin)
                connection.putheader('Content-Type', 'application/json')
                connection.putheader('Content-Length', '2')
                if duplicate not in ('Host', 'Origin', 'Content-Length'):
                    connection.putheader(duplicate, 'first')
                connection.putheader(duplicate, origin[7:] if duplicate == 'Host' else
                    origin if duplicate == 'Origin' else '2' if duplicate == 'Content-Length' else 'second')
                connection.endheaders(b'{}')
                response = connection.getresponse()
                response.read()
                verify('duplicate header rejected: ' + duplicate, response.status == 400)
                connection.close()
            for filename, data in (('../escape.csv', b'a,b\n'), ('invalid.xlsx', b'not a ZIP'), ('invalid.csv', b'a,b\n')):
                status, _, body = request(server, 'POST', '/api/runs', {
                    'files': [{'name': filename, 'contentBase64': base64.b64encode(data).decode()}],
                    'metadata': {}}, auth)
                failed = json.loads(body)
                verify('invalid upload fails: ' + filename, status == 201 and failed['status'] == 'failed'
                    and not (failed['report'].get('coverage') or {}).get('complete'))
                verify('invalid upload cannot be approved: ' + filename, request(server, 'POST',
                    '/api/runs/' + failed['id'] + '/approve', {'acknowledged': True,
                     'reviewNote': 'Isolated test must never approve an invalid source.'}, auth)[0] == 422)
            verify('traversal creates no outside file', not (directory / 'escape.csv').exists()
                and not (work.directory / 'runs/escape.csv').exists())
            source = directory / 'isolated-native.xlsx'
            values = [str(value).replace('隔离测试申请人', work.profile['inScopeApplicantNames'][0]) for value in fixtures.VALUES]
            fixtures.fixture(source, headers=['序号', *fixtures.HEADERS], values=['1', *values])
            metadata = dict(sourceUrl=admin.SOURCE, searchQuery='隔离测试检索',
                timeFrom='2024-01-01', timeTo='2026-11-03', executedAt='2026-11-03T17:08:19+08:00',
                totalResults=1, resultCountBasis='publications', resultPageCount=1, resultPageSize=20,
                expectedExportBatches=1, downloadedExportBatches=1, sampledResultPages=[1],
                exportComplete=True, loginStatus='authenticated')
            status, _, body = request(server, 'POST', '/api/runs', {
                'files': [{'name': source.name, 'contentBase64': base64.b64encode(source.read_bytes()).decode()}],
                'metadata': metadata, 'reviewed': True, 'createdBy': 'forged-actor', 'status': 'approved'}, auth)
            run = json.loads(body)
            verify('native fixture produces review-required record', status == 201 and run['status'] == 'review-required')
            verify('client cannot forge approval or administrator', run['createdBy'] == USERNAME and 'approvedAt' not in run)
            verify('source SHA computed by server', run['sourceFiles'][0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest())
            verify('sampled page audit retained', run['report']['metadata']['sampledResultPages'] == [1])
            endpoint = '/api/runs/' + run['id']
            verify('unreviewed public summary denied', request(server, 'GET', endpoint + '/public-summary', headers={'Cookie': cookie})[0] == 403)
            verify('approval needs explicit acknowledgement', request(server, 'POST', endpoint + '/approve',
                {'reviewNote': 'Isolated review needs a separate explicit acknowledgement.'}, auth)[0] == 422)
            verify('approval needs meaningful review note', request(server, 'POST', endpoint + '/approve',
                {'acknowledged': True, 'reviewNote': 'x'}, auth)[0] == 400)
            status, _, body = request(server, 'POST', endpoint + '/approve', {'acknowledged': True,
                'reviewNote': '隔离测试：仅核对测试来源与覆盖，不代表真实业务数据人工审核。'}, auth)
            approval = json.loads(body)
            verify('authenticated explicit review creates baseline', status == 200 and approval['status'] == 'approved')
            status, _, body = request(server, 'GET', endpoint + '/public-summary', headers={'Cookie': cookie})
            summary = json.loads(body)
            verify('approved summary excludes private records', status == 200 and not any(key in summary
                for key in ('metadata', 'sourceFiles', 'searchQuery', 'observations', 'legalEvents', 'sourceManifest')))
            verify('repeat review cannot overwrite history', request(server, 'POST', endpoint + '/approve',
                {'acknowledged': True, 'reviewNote': 'Isolated repeat review must not overwrite prior review history.'}, auth)[0] == 409)
            for label, executed_at, expected_status in (
                ('older source execution cannot become a later observation', '2026-11-02T17:08:19+08:00', 'failed'),
                ('equal source execution is allowed for a repeated export', metadata['executedAt'], 'review-required'),
            ):
                status, _, body = request(server, 'POST', '/api/runs', {
                    'files': [{'name': source.name, 'contentBase64': base64.b64encode(source.read_bytes()).decode()}],
                    'metadata': {**metadata, 'executedAt': executed_at}, 'baselineId': approval['baselineId']}, auth)
                repeated = json.loads(body)
                verify(label, status == 201 and repeated['status'] == expected_status)
                if expected_status == 'failed':
                    verify('older source execution cannot be approved', request(server, 'POST',
                        '/api/runs/' + repeated['id'] + '/approve', {'acknowledged': True,
                         'reviewNote': 'Isolated old source must not be approved as a new observation.'}, auth)[0] == 422)
            report_path = work.run_path(run['id']) / 'report.json'
            report_path.write_text(report_path.read_text() + ' ')
            verify('report byte tampering rejected', request(server, 'GET', endpoint, headers={'Cookie': cookie})[0] == 409)
            work.sessions[cookie.split('=', 1)[1]]['expires'] = time.monotonic() - 1
            verify('expired session rejected', request(server, 'GET', '/api/session', headers={'Cookie': cookie})[0] == 401)
            next_session, next_cookie, _, _ = login(server)
            verify('logout requires CSRF', request(server, 'POST', '/api/logout', {}, {'Origin': origin, 'Cookie': next_cookie})[0] == 403)
            verify('logout succeeds', request(server, 'POST', '/api/logout', {}, {'Origin': origin,
                'Cookie': next_cookie, 'X-CSRF-Token': next_session['csrfToken']})[0] == 200)
            verify('logout revokes server-side session', request(server, 'GET', '/api/session', headers={'Cookie': next_cookie})[0] == 401)
            for number in range(5):
                verify('incorrect password rejected ' + str(number + 1), request(server, 'POST', '/api/login',
                    {'username': USERNAME, 'password': 'incorrect'}, {'Origin': origin})[0] == 401)
            verify('five failures activate rate limit', request(server, 'POST', '/api/login',
                {'username': USERNAME, 'password': PASSWORD}, {'Origin': origin})[0] == 429)

    def test_identity_permissions_and_listener(self):
        with isolated_server() as (_, work, server):
            _, cookie, _, _ = login(server)
            path = work.directory / 'administrator.json'
            original = path.read_bytes()
            identity = json.loads(original)
            identity['role'] = 'viewer'
            path.write_text(json.dumps(identity))
            verify('role change invalidates private session', request(server, 'GET', '/api/runs', headers={'Cookie': cookie})[0] == 401)
            path.write_bytes(original)
            verify('restoring identity does not resurrect revoked session', request(server, 'GET', '/api/runs', headers={'Cookie': cookie})[0] == 401)
            if sys.platform != 'win32':
                _, cookie, _, _ = login(server)
                path.chmod(0o644)
                verify('permissive identity mode fails closed', request(server, 'GET', '/api/runs', headers={'Cookie': cookie})[0] == 401)
                path.chmod(0o600)
            with self.assertRaises(ValueError):
                admin.Server(('0.0.0.0', 0), work)
            CHECKS.append('public bind refused')
            with self.assertRaises(ValueError):
                admin.initialize(ROOT / 'must-not-create-private-data', USERNAME, PASSWORD)
            verify('public repository private-data directory refused', not (ROOT / 'must-not-create-private-data').exists())

    def test_archive_safety_limits(self):
        with tempfile.TemporaryDirectory(prefix='chcnav-admin-archive-security-') as temporary:
            directory = Path(temporary)
            cases = [
                ('traversal', '../fixture.xml', b'<a/>', None),
                ('absolute-path', '/fixture.xml', b'<a/>', None),
                ('backslash', 'xl\\fixture.xml', b'<a/>', None),
                ('macro', 'xl/vbaProject.bin', b'ISOLATED', None),
                ('utf8-dtd-entity', 'xl/workbook.xml', b'<!DOCTYPE a [<!ENTITY isolated "fixture">]><a>&isolated;</a>', None),
                ('utf16-dtd-entity', 'xl/workbook.xml', '<!DOCTYPE a [<!ENTITY isolated "fixture">]><a>&isolated;</a>'.encode('utf-16'), None),
            ]
            for label, name, value, _ in cases:
                path = directory / (label + '.xlsx')
                with ZipFile(path, 'w') as archive:
                    archive.writestr(name, value)
                with self.assertRaises(ValueError, msg=label):
                    admin.validate_xlsx(path)
                CHECKS.append('unsafe XLSX rejected: ' + label)
            path = directory / 'symlink.xlsx'
            with ZipFile(path, 'w') as archive:
                entry = ZipInfo('xl/link.xml')
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, 'outside')
            with self.assertRaises(ValueError):
                admin.validate_xlsx(path)
            CHECKS.append('XLSX symlink rejected')
            path = directory / 'duplicate.xlsx'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with ZipFile(path, 'w') as archive:
                    archive.writestr('xl/fixture.xml', '<a/>')
                    archive.writestr('xl/fixture.xml', '<a/>')
            with self.assertRaises(ValueError):
                admin.validate_xlsx(path)
            CHECKS.append('XLSX duplicate entries rejected')
            path = directory / 'too-many.xlsx'
            with ZipFile(path, 'w') as archive:
                for number in range(2001):
                    archive.writestr(str(number), '')
            with self.assertRaises(ValueError):
                admin.validate_xlsx(path)
            CHECKS.append('XLSX entry-count limit enforced')
            for label, claimed_size in (('single-entry-limit', 21 * 1048576), ('total-size-limit', 81 * 1048576)):
                path = directory / (label + '.xlsx')
                with ZipFile(path, 'w') as archive:
                    archive.writestr('xl/fixture.xml', '<a/>')
                data = bytearray(path.read_bytes())
                offset = data.index(b'PK\x01\x02')
                struct.pack_into('<I', data, offset + 24, claimed_size)
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    admin.validate_xlsx(path)
                CHECKS.append('XLSX declared-size limit enforced: ' + label)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AdministratorSecurityTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(status='pass' if result.wasSuccessful() else 'fail', checks=CHECKS,
        checkCount=len(CHECKS), testCases=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        fixturesOnly=True, productionCredentialsInitialized=False, productionDataModified=False,
        externalRequests=0, backendSha256=SOURCE_SHA,
        note='Separate temporary loopback servers; no shared UI session or real source export used.')
    path = ROOT / 'reports/manual-admin-security-validation.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'checks'}, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
