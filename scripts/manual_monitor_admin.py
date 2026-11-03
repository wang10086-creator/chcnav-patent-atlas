"""Private, loopback-only administrator workbench for manual Incopat monitoring.

Create an administrator explicitly in a private console (no default password):
  python scripts/manual_monitor_admin.py init --data-dir /private/chcnav-monitor --username manager
Run on the administrator's computer:
  python scripts/manual_monitor_admin.py serve --data-dir /private/chcnav-monitor

This service never queries Incopat, schedules jobs, writes Git or publishes.
"""
import argparse
import base64
import binascii
import datetime as dt
import getpass
import hashlib
import hmac
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www-incopat-com-s-6.proxy.itic-sci.com/'
COOKIE = 'chcnav_manual_admin'
MAX_UPLOAD = 40 * 1024 * 1024
MAX_BODY = 58 * 1024 * 1024
SESSION_SECONDS = 1800
ID = re.compile(r'^[a-f0-9]{32}$')
METADATA_KEYS = {'searchQuery', 'timeFrom', 'timeTo', 'executedAt', 'sourceUrl',
                 'loginStatus', 'exportComplete', 'totalResults', 'resultCountBasis',
                 'coverageSchemaVersion', 'resultPageCount', 'resultPageSize',
                 'expectedExportBatches', 'downloadedExportBatches', 'visitedResultPages', 'sampledResultPages',
                 'exportBatches', 'expectedPages', 'downloadedPages'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    with temporary.open('x', encoding='utf-8') as out:
        os.chmod(temporary, 0o600)
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_directory(path):
    path = path.expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('管理账号、原始导出和报告必须保存在公开仓库之外')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix':
        if path.stat().st_uid != os.getuid():
            raise ValueError('私有目录必须由当前操作系统用户拥有')
        os.chmod(path, 0o700)
    return path


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1, dklen=64).hex()


def initialize(path, username, password):
    path = private_directory(path)
    if not isinstance(username, str) or not 1 <= len(username) <= 80 or any(ord(c) < 32 for c in username):
        raise ValueError('管理员名称不合法')
    if len(password) < 14 or len(password) > 256:
        raise ValueError('管理员密码须为 14 至 256 个字符')
    target = path / 'administrator.json'
    if target.exists():
        raise ValueError('管理员已初始化；不会覆盖已有账号或资料')
    salt = secrets.token_hex(32)
    value = dict(schemaVersion=1, username=username, role='administrator', salt=salt,
                 passwordHash=password_hash(password, salt), createdAt=now())
    # Exclusive creation is intentional: a second initialization must not reset an account.
    with target.open('x', encoding='utf-8') as out:
        os.chmod(target, 0o600)
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return value


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def validate_xlsx(path):
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or len({e.filename for e in entries}) != len(entries):
                raise ValueError('XLSX 项目过多或包含重复项目')
            if sum(e.file_size for e in entries) > 80 * 1024 * 1024:
                raise ValueError('XLSX 展开后超过 80 MiB 限制')
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in entry.filename:
                    raise ValueError('XLSX 包含不安全路径')
                if entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('不接受加密或符号链接 XLSX 项目')
                if entry.file_size > 20 * 1024 * 1024 or 'vbaproject' in entry.filename.lower():
                    raise ValueError('不接受宏或超过 20 MiB 的单个 XLSX 项目')
                if entry.filename.endswith(('.xml', '.rels')):
                    value = archive.read(entry).replace(b'\x00', b'').upper()
                    if b'<!DOCTYPE' in value or b'<!ENTITY' in value:
                        raise ValueError('不接受 XML 实体或外部文档声明')
    except BadZipFile as error:
        raise ValueError('XLSX ZIP 文件损坏') from error


class Workbench:
    def __init__(self, data_dir, session_seconds=SESSION_SECONDS, profile_id='chcnav'):
        self.directory = private_directory(data_dir)
        self.sessions, self.attempts = {}, {}
        self.lock = threading.RLock()
        self.import_lock = threading.Lock()
        self.session_seconds = session_seconds
        self.config = read_json(ROOT / 'site-overrides/data/monitor-config.json')
        self.profile = next((p for p in self.config['profiles'] if p['id'] == profile_id), None)
        if not self.profile:
            raise ValueError('监控对象未配置可靠的申请人范围')
        self.baseline = ROOT / '_site/data/portfolio-current.json'
        if not self.baseline.is_file():
            raise ValueError('请先构建本地预览，生成 _site/data/portfolio-current.json')
        for name in ('runs', 'baselines'):
            (self.directory / name).mkdir(exist_ok=True, mode=0o700)

    def identity(self):
        path = self.directory / 'administrator.json'
        if not path.is_file() or path.is_symlink():
            return None
        if os.name == 'posix' and (path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid()):
            return None
        try:
            value = read_json(path)
            if value.get('role') != 'administrator' or not isinstance(value.get('username'), str) or not re.fullmatch(r'[a-f0-9]{64}', value.get('salt', '')) or not re.fullmatch(r'[a-f0-9]{128}', value.get('passwordHash', '')):
                return None
            return value
        except (ValueError, OSError, TypeError):
            return None

    def authenticate(self, username, password):
        identity = self.identity()
        if not identity:
            raise Problem(503, '管理员尚未初始化或私有账号配置无效；请在受控终端运行 init')
        with self.lock:
            recent = [x for x in self.attempts.get('loopback', []) if time.monotonic() - x < 300]
            self.attempts['loopback'] = recent
            if len(recent) >= 5:
                raise Problem(429, '登录尝试过多，请五分钟后再试')
            if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
                raise Problem(401, '管理员名称或密码错误')
            derived = password_hash(password, identity['salt'])
            if not hmac.compare_digest(username.encode('utf-8'), identity['username'].encode('utf-8')) or not hmac.compare_digest(derived, identity['passwordHash']):
                recent.append(time.monotonic())
                raise Problem(401, '管理员名称或密码错误')
            self.attempts['loopback'] = []
            sid = secrets.token_urlsafe(48)
            session = dict(user=dict(username=identity['username'], role='administrator'),
                           csrfToken=secrets.token_urlsafe(40), expires=time.monotonic() + self.session_seconds,
                           expiresAt=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=self.session_seconds)).isoformat(),
                           identityDigest=digest(self.directory / 'administrator.json'))
            self.sessions[sid] = session
            return sid, session

    def session(self, sid):
        with self.lock:
            value = self.sessions.get(sid)
            if not value or value['expires'] <= time.monotonic() or not self.identity() or value['identityDigest'] != digest(self.directory / 'administrator.json'):
                self.sessions.pop(sid, None)
                raise Problem(401, '需要有效的管理员登录')
            return value

    def run_path(self, run_id):
        if not ID.fullmatch(run_id):
            raise Problem(404, '核查批次不存在')
        path = self.directory / 'runs' / run_id
        if not path.is_dir() or path.is_symlink():
            raise Problem(404, '核查批次不存在')
        return path

    def run(self, run_id):
        path = self.run_path(run_id)
        value = read_json(path / 'state.json')
        report_path = path / 'report.json'
        if value.get('reportSha256') != digest(report_path):
            raise Problem(409, '私有报告校验值已变化，禁止读取或审核为可信结果')
        value['report'] = read_json(report_path)
        value['coverage'] = value['report'].get('coverage')
        return value

    def baselines(self):
        values = []
        for path in (self.directory / 'baselines').glob('*.json'):
            if path.is_symlink() or not ID.fullmatch(path.stem):
                continue
            snapshot = read_json(path)
            if snapshot.get('profile', {}).get('id') != self.profile['id']:
                continue
            values.append(dict(id=path.stem, label=snapshot.get('label', path.stem),
                               reviewedAt=snapshot.get('reviewedAt'), profileId=snapshot.get('profile', {}).get('id')))
        return sorted(values, key=lambda x: x.get('reviewedAt') or '', reverse=True)

    def import_run(self, payload, actor):
        if not self.import_lock.acquire(blocking=False):
            raise Problem(409, '已有管理员核查批次正在处理，请稍后重试')
        try:
            return self._import_run(payload, actor)
        finally:
            self.import_lock.release()

    def _import_run(self, payload, actor):
        files = payload.get('files')
        supplied = payload.get('metadata')
        if not isinstance(files, list) or not 1 <= len(files) <= 30 or not isinstance(supplied, dict):
            raise Problem(400, '需要 1 至 30 个导出文件及实际执行元数据')
        metadata = {k: v for k, v in supplied.items() if k in METADATA_KEYS}
        metadata.setdefault('sourceUrl', SOURCE)
        metadata['coverageSchemaVersion'] = 2
        run_id = uuid.uuid4().hex
        path = self.directory / 'runs' / run_id
        sources = path / 'sources'
        sources.mkdir(parents=True, mode=0o700)
        created = now()
        state = dict(id=run_id, status='importing', createdAt=created,
                     createdBy=actor['username'], administratorIdentity='private-local-administrator',
                     profileId=self.profile['id'], published=False)
        write_json(path / 'state.json', state)
        try:
            total_bytes, saved = 0, []
            for i, item in enumerate(files):
                name = item.get('name', '') if isinstance(item, dict) else ''
                if not isinstance(name, str) or not 1 <= len(name) <= 180 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name) or Path(name).suffix.lower() not in ('.csv', '.tsv', '.xlsx'):
                    raise ValueError('导出文件名或类型不合法')
                encoded = item.get('contentBase64')
                if not isinstance(encoded, str) or len(encoded) > MAX_BODY:
                    raise ValueError('导出文件内容无效或过大')
                data = base64.b64decode(encoded, validate=True)
                total_bytes += len(data)
                if total_bytes > MAX_UPLOAD:
                    raise ValueError('单批原文件超过 40 MiB；不能通过删减记录凑覆盖')
                dest = sources / (f'{i + 1:03}-' + name)
                with dest.open('xb') as out:
                    os.chmod(dest, 0o600)
                    out.write(data)
                if dest.suffix.lower() == '.xlsx':
                    validate_xlsx(dest)
                saved.append((name, dest))
            state['sourceFiles'] = [dict(name=name, storedName=p.name, sha256=digest(p), bytes=p.stat().st_size,
                                         importedAt=created) for name, p in saved]
            write_json(path / 'source-files.json', state['sourceFiles'])
            previous_id = payload.get('baselineId')
            previous = None
            if previous_id:
                if not isinstance(previous_id, str) or not ID.fullmatch(previous_id):
                    raise ValueError('观察基线编号无效')
                previous = self.directory / 'baselines' / (previous_id + '.json')
                if not previous.is_file() or previous.is_symlink():
                    raise ValueError('只能选择本工作台已由管理员审核保存的观察基线')
                snapshot = read_json(previous)
                if snapshot.get('reviewed') is not True or snapshot.get('reviewedBy') is None or snapshot.get('profile', {}).get('id') != self.profile['id']:
                    raise ValueError('观察基线缺少已验证的管理员审核记录')
                try:
                    execution = dt.datetime.fromisoformat(str(metadata.get('executedAt', '')).replace('Z', '+00:00'))
                    prior_time = dt.datetime.fromisoformat(str(snapshot.get('checkedAt', '')).replace('Z', '+00:00'))
                    if execution.tzinfo is None or prior_time.tzinfo is None:
                        raise ValueError('来源核查时间必须带时区')
                    if execution < prior_time:
                        raise ValueError('本批来源执行时间早于已审核基线，不能作为后续状态变化核查')
                except (ValueError, TypeError) as error:
                    raise ValueError('对照基线与本批来源执行时间无法可靠比较：' + str(error)) from error
                state['comparedBaselineId'] = previous_id
            audit = payload.get('exportAudit')
            source_manifest = payload.get('sourceManifest')
            if source_manifest is not None:
                if not isinstance(source_manifest, dict):
                    raise ValueError('原始批次清单必须为 JSON 对象')
                if source_manifest.get('searchQuery') != metadata.get('searchQuery') or source_manifest.get('totalResults') != metadata.get('totalResults'):
                    raise ValueError('所交接清单的检索式或来源总数与本次实际元数据不一致')
                write_json(path / 'provided-source-manifest.json', source_manifest)
            if all(p.suffix.lower() == '.xlsx' for _, p in saved):
                from incopat_xlsx_native import native_xlsx_rows
                from prepare_incopat_exports import prepare
                batches = []
                if source_manifest:
                    declared = source_manifest.get('batches')
                    incoming = [name for name, _ in saved]
                    if not isinstance(declared, list) or len(declared) != len(saved) or sorted(str(b.get('path', '')).replace('\\', '/').split('/')[-1] for b in declared) != sorted(incoming):
                        raise ValueError('原始批次清单与实际上传文件不一一对应，不能忽略未交接文件')
                for name, source in saved:
                    parsed = native_xlsx_rows(source)
                    if parsed is None:
                        raise ValueError('工作台原生 XLSX 通道仅接受可核对下载简介的 Incopat 原生批次；其他格式请准备规范 CSV 和审计')
                    _, info = parsed
                    bounds = info.get('sourceRange')
                    # Native helper intentionally keeps raw introduction rather than guessing.
                    if not bounds:
                        from incopat_xlsx_native import read_workbook
                        book = read_workbook(source)
                        intro = {}
                        for sheet in book['sheets']:
                            if sheet['name'] == '下载简介':
                                for row in sheet['rows']:
                                    cols = {re.match('[A-Z]+', k).group(): v['value'] for k, v in row['cells'].items()}
                                    if cols.get('A'):
                                        intro[cols['A']] = cols.get('B', '')
                            elif sheet['name'] != info['worksheet'] and any(r['cells'] for r in sheet['rows']):
                                raise ValueError('原生 XLSX 存在未确认用途的非空工作表')
                        bounds = intro.get('数据范围')
                    matching = []
                    if source_manifest:
                        matching = [b for b in source_manifest.get('batches', [])
                                    if str(b.get('path', '')).replace('\\', '/').split('/')[-1] == name]
                    if len(matching) > 1 or matching and matching[0].get('range') != bounds:
                        raise ValueError('所交接的清单与实际原文件范围不一致')
                    batch = dict(path=str(source), range=bounds)
                    if matching and matching[0].get('downloadedAt'):
                        batch['downloadedAt'] = matching[0]['downloadedAt']
                    batches.append(batch)
                manifest = dict(searchQuery=metadata.get('searchQuery'), totalResults=metadata.get('totalResults'),
                                resultPageCount=metadata.get('resultPageCount'), resultPageSize=metadata.get('resultPageSize'),
                                expectedExportBatches=metadata.get('expectedExportBatches'), batches=batches)
                write_json(path / 'batches.json', manifest)
                audit = prepare(path / 'batches.json', path / 'prepared')
                canonical = path / 'prepared/incopat-canonical.csv'
                metadata['resultCountBasis'] = 'publications'
                state['receivedExportFileCount'] = len(saved)
            elif len(saved) == 1 and saved[0][1].suffix.lower() in ('.csv', '.tsv'):
                canonical = saved[0][1]
            else:
                raise ValueError('请导入一组原生 XLSX 批次，或一个规范 CSV／TSV；不能混合不同格式凑覆盖')
            audit_path = None
            if audit is not None:
                if not isinstance(audit, dict):
                    raise ValueError('适配审计必须是 JSON 对象')
                audit_path = path / 'export-audit.json'
                write_json(audit_path, audit)
            write_json(path / 'run-metadata.json', metadata)
            command = [sys.executable, str(ROOT / 'scripts/import_incopat.py'),
                       '--export', str(canonical), '--metadata', str(path / 'run-metadata.json'),
                       '--baseline', str(self.baseline), '--profile', self.profile['id'], '--output', str(path / 'report.json')]
            if audit_path:
                command += ['--export-audit', str(audit_path)]
            if previous:
                command += ['--previous', str(previous)]
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=150)
            if process.returncode not in (0, 2) or not (path / 'report.json').is_file():
                raise ValueError('解析或比对进程失败，未产生可审核报告')
            report = read_json(path / 'report.json')
            state.update(status='review-required' if not report.get('anomalies') and report.get('coverage', {}).get('complete') else 'failed',
                         counts=report.get('counts', {}), reportSha256=digest(path / 'report.json'))
        except (ValueError, KeyError, TypeError, OSError, binascii.Error, subprocess.TimeoutExpired) as error:
            report = dict(schemaVersion=1, kind='incopat-review-report', runState='import-failed',
                          runStateLabel='执行异常，未完成核查', metadata=metadata, counts={},
                          anomalies=[dict(type='private-import-failed', reason=str(error))],
                          coverage=dict(complete=False), publicationState='review-only-not-published')
            write_json(path / 'report.json', report)
            state.update(status='failed', counts={}, reportSha256=digest(path / 'report.json'))
        write_json(path / 'state.json', state)
        return self.run(run_id)

    def review(self, run_id, actor, payload, approve):
        with self.lock:
            run = self.run(run_id)
            if run['status'] not in ('review-required', 'failed'):
                raise Problem(409, '该批次已审核，不能覆盖既有审核记录')
            path = self.run_path(run_id)
            note = payload.get('reviewNote' if approve else 'reason', '')
            if not isinstance(note, str) or not 10 <= len(note.strip()) <= 2000:
                raise Problem(400, '请填写至少 10 字的实际核对或退回原因')
            if approve:
                report = run['report']
                if payload.get('acknowledged') is not True or report.get('anomalies') or report.get('coverage', {}).get('complete') is not True or run['status'] != 'review-required':
                    raise Problem(422, '只有覆盖完整、无异常且明确人工核对的结果才能成为观察基线')
                bridge = "const c=require(process.argv[1]);let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>console.log(JSON.stringify(c.makeSnapshot(JSON.parse(s),true))));"
                result = subprocess.run(['node', '-e', bridge, str(ROOT / 'site-overrides/patent-monitor-core.js')],
                                        input=json.dumps(report, ensure_ascii=False), text=True, encoding='utf-8', capture_output=True, timeout=45)
                if result.returncode:
                    raise Problem(422, '审核基线生成失败，未更改批次审核状态')
                snapshot = json.loads(result.stdout)
                baseline_id = uuid.uuid4().hex
                snapshot.update(reviewedBy=actor['username'], reviewedAt=now(), runId=run_id,
                                sourceReportSha256=run['reportSha256'],
                                label=report.get('metadata', {}).get('executedAt', run['createdAt']) + ' · 已审核手动核查')
                write_json(self.directory / 'baselines' / (baseline_id + '.json'), snapshot)
                run.update(status='approved', baselineId=baseline_id, approvedAt=now(), reviewedAt=now(), reviewedBy=actor['username'], reviewNote=note.strip())
            else:
                run.update(status='rejected', reviewedAt=now(), reviewedBy=actor['username'], reviewNote=note.strip())
            run.pop('report', None)
            run.pop('coverage', None)
            write_json(path / 'state.json', run)
            return self.run(run_id)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, workbench):
        if address[0] != '127.0.0.1':
            raise ValueError('本机私有工作台只允许绑定 127.0.0.1')
        self.workbench = workbench
        super().__init__(address, Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    server_version = 'PrivateManualMonitor'

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_args):
        # Do not log query strings, credentials, filenames, cookies or request bodies.
        return

    def output(self, status, value, content_type='application/json; charset=utf-8', cookie=None, filename=None):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def check_host(self):
        for header in ('Host', 'Origin', 'Content-Length', 'Transfer-Encoding', 'Cookie', 'X-CSRF-Token'):
            if len(self.headers.get_all(header, [])) > 1:
                raise Problem(400, '不接受重复或歧义的管理请求头')
        expected = self.server.origin.removeprefix('http://')
        if self.headers.get('Host') != expected or not ipaddress.ip_address(self.client_address[0]).is_loopback:
            raise Problem(403, '管理工作台仅接受准确的本机访问地址')
        # A public-site link may navigate to the non-sensitive login shell.
        # This exception grants no session and never applies to private APIs.
        if self.command == 'GET' and urlsplit(self.path).path == '/' and self.headers.get('Sec-Fetch-Mode') == 'navigate' and self.headers.get('Sec-Fetch-Dest') == 'document':
            return
        if self.headers.get('Origin') not in (None, self.server.origin):
            raise Problem(403, '不接受跨站管理请求')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem(403, '不接受跨站管理请求')

    def require_session(self, mutation=False):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            sid = jar[COOKIE].value if COOKIE in jar else ''
        except cookies.CookieError:
            sid = ''
        session = self.server.workbench.session(sid)
        if mutation:
            if self.headers.get('Origin') != self.server.origin:
                raise Problem(403, '管理写操作必须来自当前工作台')
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), session['csrfToken'].encode('utf-8')):
                raise Problem(403, '管理请求缺少有效的防伪令牌')
        return sid, session

    def body(self, limit=MAX_BODY):
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding'):
            raise Problem(400, '不接受编码或分块请求体')
        if self.headers.get_content_type() != 'application/json':
            raise Problem(415, '仅接受 JSON 请求')
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise Problem(400, '请求大小无效')
        if not 0 < size <= limit:
            raise Problem(413, '请求过大或缺少实际内容长度')
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            raise Problem(400, 'JSON 无法完整解析')
        if not isinstance(value, dict):
            raise Problem(400, '请求内容必须为对象')
        return value

    def handle_error(self, error):
        if isinstance(error, Problem):
            self.output(error.status, dict(error=error.message))
        else:
            self.output(500, dict(error='管理请求失败；未发布或更改网站，请检查私有工作台状态'))

    def do_GET(self):
        try:
            self.check_host()
            path = urlsplit(self.path).path
            static = {'/': ROOT / 'admin-ui/index.html', '/static/admin.js': ROOT / 'admin-ui/admin.js',
                      '/static/admin.css': ROOT / 'admin-ui/admin.css'}
            if path in static:
                target = static[path]
                if not target.is_file():
                    raise Problem(503, '私有管理员界面尚未安装')
                kind = 'text/html; charset=utf-8' if path == '/' else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
                self.output(200, target.read_bytes(), kind)
                return
            work = self.server.workbench
            if path == '/api/session' and not work.identity():
                raise Problem(503, '管理员尚未初始化；请在私有终端配置账号后登录')
            sid, session = self.require_session()
            if path == '/api/session':
                self.output(200, {k: session[k] for k in ('user', 'csrfToken', 'expiresAt')})
            elif path == '/api/config':
                docs = read_json(work.baseline)
                names = set(work.profile['inScopeApplicantNames'])
                docs = [d for d in docs if any(n.strip() in names for n in str(d.get('applicants', '')).replace('；', ';').split(';'))]
                self.output(200, dict(profile=work.profile, source=work.config['source'],
                                      baselineCounts=dict(documents=len(docs), applications=len({d['applicationNumber'] for d in docs})),
                                      maxUploadBytes=MAX_UPLOAD, baselines=work.baselines(), mode='manual-private-local'))
            elif path == '/api/runs':
                values = [read_json(p) for p in (work.directory / 'runs').glob('*/state.json')]
                values = [v for v in values if v.get('profileId') == work.profile['id']]
                self.output(200, dict(runs=sorted(values, key=lambda x: x['createdAt'], reverse=True)))
            else:
                match = re.fullmatch(r'/api/runs/([a-f0-9]{32})(?:/(report|public-summary))?', path)
                baseline = re.fullmatch(r'/api/baselines/([a-f0-9]{32})', path)
                if match:
                    run = work.run(match[1])
                    if match[2] == 'report':
                        self.output(200, run['report'], filename=f'incopat-review-{run["id"]}.json')
                    elif match[2] == 'public-summary':
                        if run['status'] != 'approved':
                            raise Problem(403, '只有已审核结果可以导出脱敏公开摘要')
                        summary = dict(schemaVersion=1, mode='manual', competitor=work.profile['name'],
                                       checkedAt=run['report'].get('metadata', {}).get('executedAt'), reviewedAt=run['reviewedAt'],
                                       counts=run['report'].get('counts'), source='Incopat', sourceUrl=SOURCE,
                                       sourceReportSha256=run['reportSha256'],
                                       publicationState='approved-for-review-not-published',
                                       notice='管理员已核对该批资料；不等于官方法律状态核验，也未自动发布网站。')
                        self.output(200, summary, filename=f'incopat-approved-summary-{run["id"]}.json')
                    else:
                        self.output(200, run)
                elif baseline:
                    target = work.directory / 'baselines' / (baseline[1] + '.json')
                    if not target.is_file() or target.is_symlink():
                        raise Problem(404, '已审核观察基线不存在')
                    self.output(200, read_json(target), filename=f'incopat-baseline-{baseline[1]}.json')
                else:
                    raise Problem(404, '资源不存在')
        except (Problem, ValueError, OSError, KeyError, TypeError) as error:
            self.handle_error(error)

    def do_POST(self):
        try:
            self.check_host()
            path = urlsplit(self.path).path
            work = self.server.workbench
            if path == '/api/login':
                if self.headers.get('Origin') != self.server.origin:
                    raise Problem(403, '登录必须来自当前私有工作台')
                value = self.body(8192)
                sid, session = work.authenticate(value.get('username'), value.get('password'))
                self.output(200, {k: session[k] for k in ('user', 'csrfToken', 'expiresAt')},
                            cookie=f'{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={work.session_seconds}')
                return
            sid, session = self.require_session(mutation=True)
            if path == '/api/logout':
                work.sessions.pop(sid, None)
                self.output(200, dict(loggedOut=True), cookie=f'{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            elif path == '/api/runs':
                self.output(201, work.import_run(self.body(), session['user']))
            else:
                match = re.fullmatch(r'/api/runs/([a-f0-9]{32})/(approve|reject)', path)
                if not match:
                    raise Problem(404, '管理操作不存在')
                self.output(200, work.review(match[1], session['user'], self.body(16384), match[2] == 'approve'))
        except (Problem, ValueError, OSError, KeyError, TypeError) as error:
            self.handle_error(error)

    def do_OPTIONS(self):
        self.output(403, dict(error='管理工作台不开放跨站接口'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('init', 'serve'))
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--username', default='manager')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--profile', default='chcnav', help='配置中的精确监控对象标识')
    args = parser.parse_args()
    if args.operation == 'init':
        password = getpass.getpass('设置本地管理员密码（不会回显）：')
        if password != getpass.getpass('再次输入：'):
            parser.error('两次密码不一致')
        initialize(args.data_dir, args.username, password)
        print('管理员已在私有目录初始化。账号不会上传至 GitHub 或 Incopat。')
    else:
        server = Server(('127.0.0.1', args.port), Workbench(args.data_dir, profile_id=args.profile))
        print(f'私有管理员工作台：{server.origin}/', flush=True)
        print('仅本机可访问；无自动任务、无 Incopat API、无网站发布。', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()


if __name__ == '__main__':
    main()
