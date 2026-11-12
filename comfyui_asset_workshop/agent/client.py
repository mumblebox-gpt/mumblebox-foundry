"""Local HTTP client shared by the stdio tools; no models or project writes here."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid


class APIError(ValueError):
    def __init__(self, status, details):
        self.status, self.details = status, details
        super().__init__(f'HTTP {status}: {details.get("error", "Mumblebox request failed")}')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value):
        raise ValueError('Use a recorded project, image or artifact ID, not a file path.')
    return value


class LocalAPI:
    def __init__(self, base_url='http://127.0.0.1:8188', *, input_roots=(), input_files=()):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Connect to this computer’s Comfy HTTP address only.')
        self.base_url = base_url.rstrip('/') + '/asset-workshop/v2'
        self.headers = {}
        self.input_roots = [Path(p).resolve(strict=True) for p in input_roots]
        self.input_files = {Path(p).resolve(strict=True) for p in input_files}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, body=None, method=None, content_type=None, *, binary=False, content_length=None, timeout=120):
        if not path.startswith('/') or '\\' in path or '..' in path:
            raise ValueError('Use a supported local Mumblebox action.')
        data = body if isinstance(body, bytes) or hasattr(body, 'read') else json.dumps(body).encode() if body is not None else None
        headers = dict(self.headers)
        if data is not None:
            headers['Content-Type'] = content_type or 'application/json'
        if content_length is not None:
            headers['Content-Length'] = str(content_length)
        request = urllib.request.Request(self.base_url+path, data=data, headers=headers,
                                         method=method or ('POST' if body is not None else 'GET'))
        try:
            with self.opener.open(request, timeout=timeout) as response:
                content = response.read((4*1024**2 if binary else 1024**2)+1)
        except urllib.error.HTTPError as error:
            payload = error.read(32768)
            try:
                details = json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                details = {'error': error.reason}
            raise APIError(error.code, details) from None
        if len(content) > (4*1024**2 if binary else 1024**2):
            raise ValueError('This response exceeds the metadata/preview limit. Download the recorded artifact directly.')
        return content if binary else json.loads(content)

    def project_path(self, project_id, suffix=''):
        return f'/projects/{identifier(project_id)}{suffix}'

    def get_project(self, project_id=None):
        return self.request(self.project_path(project_id)) if project_id else {
            'state': 'fresh', 'instruction': 'Create a new project or explicitly reuse History; no old project restored.',
            **self.request('/capabilities')}

    def save_project(self, project_id=None, expected_revision=0, changes=None):
        if not project_id:
            project = self.request('/projects', {})
            if not changes:
                return project
            project_id, expected_revision = project['id'], project['revision']
        return self.request(self.project_path(project_id), {'expected_revision': expected_revision, 'changes': changes or {}}, 'PATCH')

    def save_pipeline(self, project_id, expected_revision, changes):
        return self.request(self.project_path(project_id,'/pipeline'),{'expected_revision':expected_revision,'changes':changes},'PATCH')

    def select_pipeline_artifact(self,project_id,expected_revision,artifact_id):
        return self.request(self.project_path(project_id,'/pipeline/select'),{'expected_revision':expected_revision,'artifact_id':identifier(artifact_id)})

    def create_material_session(self,project_id,expected_revision,source_id,settings=None):
        return self.request(self.project_path(project_id,'/materials'),{'expected_revision':expected_revision,'source_id':identifier(source_id),'settings':settings or {}})

    def get_material_session(self,project_id,session_id):
        return self.request(self.project_path(project_id,'/materials/'+identifier(session_id)))

    def get_material_selection(self,project_id,session_id,mask_id):
        return self.request(self.project_path(project_id,'/materials/'+identifier(session_id)+'/selections/'+identifier(mask_id)))

    def save_material_choices(self,project_id,session_id,expected_draft_revision,state):
        return self.request(self.project_path(project_id,'/materials/'+identifier(session_id)),{'expected_draft_revision':expected_draft_revision,'state':state},'PATCH')

    def allowed_input(self, path):
        resolved = Path(path).resolve(strict=True)
        if resolved not in self.input_files and not any(resolved.is_relative_to(root) for root in self.input_roots):
            raise ValueError('This input file was not authorized. Add its exact --input-file or an approved --input-root to the server launch.')
        if not resolved.is_file() or resolved.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp') or resolved.stat().st_size > 64*1024**2:
            raise ValueError('Choose an authorized PNG, JPEG or WebP image below 64 MiB.')
        return resolved

    def multipart(self, fields, file_field, path):
        boundary = 'mumblebox-' + uuid.uuid4().hex
        parts = []
        for key, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        filename = 'input' + path.suffix.lower()
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
                  path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
        return b''.join(parts), f'multipart/form-data; boundary={boundary}'

    def import_image(self, project_id, expected_revision, path, role='source'):
        data, content_type = self.multipart({'expected_revision': expected_revision, 'role': role}, 'image', self.allowed_input(path))
        return self.request(self.project_path(project_id, '/images'), data, content_type=content_type)

    def prepare_edit(self, project_id, expected_revision, role, revision_id, mask_path, instruction, feather=0, replace_detail=False):
        data, content_type = self.multipart({'expected_revision': expected_revision, 'role': role, 'revision_id': identifier(revision_id),
            'prompt': instruction, 'feather': feather, 'replace_detail': str(replace_detail).lower()}, 'mask', self.allowed_input(mask_path))
        return self.request(self.project_path(project_id, '/edits'), data, content_type=content_type)

    def start_job(self, project_id, expected_revision, kind, request_key, payload=None):
        return self.request(self.project_path(project_id, '/jobs'), {'expected_revision': expected_revision,
            'kind': kind, 'request_key': identifier(request_key), 'payload': payload or {}})

    def get_job(self, project_id, job_id):
        return self.request(self.project_path(project_id, f'/jobs/{identifier(job_id)}'))

    def cancel_job(self, project_id, job_id):
        return self.request(self.project_path(project_id, f'/jobs/{identifier(job_id)}/cancel'), {})

    def review_image(self, project_id, expected_revision, role, revision_id, sha256, decision, notes=''):
        return self.request(self.project_path(project_id, '/reviews'), {'expected_revision': expected_revision, 'role': role,
            'revision_id': identifier(revision_id), 'sha256': sha256, 'decision': decision, 'notes': notes, 'reviewer': 'agent'})

    def read_artifact(self, project_id, artifact_id, mode='metadata'):
        path = self.project_path(project_id, f'/artifacts/{identifier(artifact_id)}')
        metadata = self.request(path+'?metadata=1')
        if mode not in ('metadata', 'preview', 'full'):
            raise ValueError('Choose metadata, preview or full.')
        result = {'metadata': metadata, 'uri': f'mumblebox://projects/{project_id}/artifacts/{artifact_id}',
                  'download_url': self.base_url+path+'?download=1'}
        if mode == 'preview':
            if metadata.get('kind') != 'image':
                raise ValueError('Preview mode is for images. Inspect a mesh in the visible 3D viewer or download its GLB.')
            result['preview'] = self.request(path+'?preview=1', binary=True)
        return result

    def export_package(self, project_id, expected_revision, artifact_ids, audience="agent"):
        return self.request(self.project_path(project_id, '/packages'), {'expected_revision': expected_revision,
            'artifact_ids': [identifier(i) for i in artifact_ids], 'audience':audience})

    def release_models(self):
        return self.request('/release', {})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
