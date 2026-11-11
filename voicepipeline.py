"""VoicePipeline owns enrolment and recognition; Declan never copies its profiles."""
import base64
import json
import os
import re
from http.client import HTTPException
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE = 4 * 1024 * 1024
WRITE_LOCK = Lock()


class PipelineError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(method, path, body=None, *, audio=False):
    base = os.environ.get('DECLAN_VOICEPIPELINE_URL', '').strip().rstrip('/')
    try:
        target = urlsplit(base)
    except ValueError:
        raise PipelineError('Set a valid DECLAN_VOICEPIPELINE_URL.', 503) from None
    if (target.scheme not in {'http', 'https'} or not target.hostname or target.username
            or target.password or target.query or target.fragment or target.path):
        raise PipelineError('Set DECLAN_VOICEPIPELINE_URL to the VoicePipeline server address.', 503)
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Accept': 'audio/wav' if audio else 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    token = os.environ.get('DECLAN_VOICEPIPELINE_TOKEN', '').strip()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        # Do not send LAN audio or credentials through an environment proxy or redirect.
        with build_opener(ProxyHandler({}), NoRedirect()).open(
                Request(base + path, data=data, headers=headers, method=method), timeout=8) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise PipelineError('VoicePipeline returned too much data. Open its own review page.')
            if audio:
                if len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
                    raise PipelineError('VoicePipeline did not return a WAV recording.')
                return {'audio': base64.b64encode(raw).decode()}
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        status = error.code
        error.close()
        if status == 409:
            raise PipelineError('This recording changed. Refresh before reviewing it again.', 409) from None
        if status == 404:
            raise PipelineError('This recording or speaker no longer exists. Refresh the list.', 404) from None
        raise PipelineError('VoicePipeline rejected the request. Refresh before retrying.') from None
    except (URLError, OSError, ValueError, HTTPException):
        # A write may have committed before its response was lost. Never retry it here.
        raise PipelineError('Could not confirm the VoicePipeline result. Refresh before retrying.') from None


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Choose a valid recording or speaker.')
    return value


def rows(path, fields):
    values = request('GET', path)
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise PipelineError('VoicePipeline returned an invalid list.')
    return [{key: row.get(key) for key in fields} for row in values]


def speakers():
    return rows('/api/v1/speakers', ('id', 'name', 'reference_clip_count', 'interaction_count',
                                   'avg_confidence', 'last_active_at'))


def interactions(history=False):
    # Never forward upstream audio URLs. Playback uses the fixed, authenticated proxy.
    fields = ('id', 'recorded_at', 'transcript', 'duration_ms', 'matched_speaker',
              'match_confidence', 'status', 'current_resolution_id', 'current_assigned_to')
    return rows('/api/v1/interactions/' + ('history' if history else 'pending'), fields)


def listing():
    return {'profiles': speakers(), 'interactions': interactions(), 'recogniser_connected': True,
            'notice': 'Profiles and reference recordings are managed by VoicePipeline. '
                      'Use a satellite, then refresh to review its recording. This connection does not verify live recognition.'}


def manage(body):
    if not isinstance(body, dict):
        raise ValueError('Choose a VoicePipeline operation.')
    operation = body.get('operation')
    if operation == 'history':
        return {'interactions': interactions(history=True)}
    if operation == 'audio':
        return request('GET', '/api/v1/audio/' + identifier(body.get('interaction_id')), audio=True)
    if operation not in {'resolve', 'correct', 'delete_speaker', 'clear_clips'}:
        raise ValueError('Choose a supported VoicePipeline operation.')
    if body.get('confirm') is not True:
        raise ValueError('Confirm before changing VoicePipeline.')
    with WRITE_LOCK:
        if operation in {'delete_speaker', 'clear_clips'}:
            speaker_id = identifier(body.get('speaker_id'))
            if not any(row['id'] == speaker_id for row in speakers()):
                raise ValueError('Refresh and choose an existing speaker.')
            path = '/api/v1/speakers/' + speaker_id
            result = request('DELETE', path) if operation == 'delete_speaker' else request('POST', path + '/clear-clips')
        else:
            interaction_id = identifier(body.get('interaction_id'))
            name = body.get('assigned_to')
            action = body.get('action')
            if operation == 'resolve' and action not in {'confirm', 'assign', 'enrol', 'dismiss'}:
                raise ValueError('Choose confirm, assign, enrol or dismiss.')
            needs_name = operation == 'resolve' and action != 'dismiss' or operation == 'correct' and name is not None
            if needs_name:
                if (not isinstance(name, str)
                        or not re.fullmatch(r"[^\W\d_][\w '\u2019-]{0,39}", name)
                        or name.casefold() in {'unknown', 'unidentified', 'none'}):
                    raise ValueError('Choose a valid speaker name.')
                names = [row['name'] for row in speakers()]
                if operation == 'resolve' and action == 'enrol':
                    if name.casefold() in {value.casefold() for value in names if isinstance(value, str)}:
                        raise ValueError('That speaker already exists. Assign the recording to their existing profile.')
                elif names.count(name) != 1:
                    raise ValueError('Refresh and choose an existing speaker.')
            else:
                name = None
            path = '/api/v1/interactions/' + interaction_id
            if operation == 'correct':
                if 'expected_resolution_id' not in body:
                    raise ValueError('Refresh History before correcting this recording.')
                expected = body['expected_resolution_id']
                if expected is not None:
                    identifier(expected)
                result = request('POST', path + '/correct', {'assigned_to': name, 'expected_resolution_id': expected})
            else:
                # Serialise Declan's writes and reject already resolved entries. The upstream
                # resolve API has no atomic stale-write token for edits from other clients.
                pending = next((row for row in interactions() if row['id'] == interaction_id), None)
                if pending is None:
                    raise PipelineError('This recording is no longer pending. Refresh the list.', 409)
                if action == 'confirm' and pending.get('matched_speaker') != name:
                    raise PipelineError('The suggested speaker changed. Refresh before confirming.', 409)
                result = request('POST', path + '/resolve', {'action': action, 'assigned_to': name})
        return {'saved': True, 'result': result}
