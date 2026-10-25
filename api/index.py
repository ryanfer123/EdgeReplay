"""Stateless Vercel API: computation only; private persistence uses Supabase."""
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone
import json
from urllib.parse import urlsplit, parse_qs
import uuid
from edge_replay.cloud import cloud_config
from edge_replay import __version__
from edge_replay.telemetry import parse_trace

MAX_BODY = 4194304


def dispatch(method, path, data=None):
    if method == 'GET' and path == '/api/cloud/config':
        return dict(cloud_config(), hosted=True), 200
    if method == 'GET' and path == '/api/health':
        return {'ok': True, 'hosted': True, 'version': __version__}, 200
    if method == 'GET' and path == '/api/recordings':
        return {'recordings': [], 'version': __version__}, 200
    if method == 'POST' and path == '/api/recordings':
        recording = parse_trace(data.get('name'), data.get('csv'))
        recording.update(id=str(uuid.uuid4()), created=datetime.now(timezone.utc).isoformat(), version=__version__)
        return recording, 201
    return {'error': 'Not found.'}, 404


class handler(BaseHTTPRequestHandler):
    def respond(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        url = urlsplit(self.path)
        routed = parse_qs(url.query).get('route', [None])[0]
        return '/api/' + routed.lstrip('/') if routed is not None else url.path

    def do_GET(self):
        try:
            value, status = dispatch('GET', self.route())
            self.respond(value, status)
        except Exception:
            self.respond({'error': 'The source could not be loaded. Try again shortly.'}, 502)

    def do_POST(self):
        origin = self.headers.get('Origin')
        # Forwarded host is supplied by Vercel; reject browser writes from another origin.
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.respond({'error': 'Cross-origin writes are not allowed.'}, 403)
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Send application/json.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Request is empty or exceeds the upload limit.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Request must be a JSON object.')
            value, status = dispatch('POST', self.route(), data)
            self.respond(value, status)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
            self.respond({'error': str(error)}, 400)
        except Exception:
            self.respond({'error': 'The source could not be loaded. Check connectivity or try another advertised date.'}, 502)
