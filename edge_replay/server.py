"""Local HTTP workspace and durable SQLite recordings."""
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import csv
import io
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
import uuid

from . import __version__
from .telemetry import canonical_json, parse_trace

WEB = Path(__file__).parent/'web'
MAX_BODY = 4*1024*1024


def connect(path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS recordings (id TEXT PRIMARY KEY, created TEXT, body TEXT)')
    return db


def export_csv(recording):
    output = io.StringIO(newline='')
    channels = [channel['name'] for channel in recording['channels']]
    fields = ['time_ms', *channels, 'expected_label', 'predicted_label']
    writer = csv.DictWriter(output, fields)
    writer.writeheader()
    for row in recording['rows']:
        item = {'time_ms':row['time_ms'], **row['values']}
        item.update({key:row.get(key,'') for key in ('expected_label','predicted_label')})
        writer.writerow(item)
    return output.getvalue().encode()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, database, **kwargs):
        self.database = database
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        super().end_headers()

    def respond(self, data, status=200, kind='application/json; charset=utf-8', filename=None):
        body = data if isinstance(data,bytes) else canonical_json(data).encode()
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        if filename:
            self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        expected = {f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}
        if self.headers.get('Host') not in expected:
            self.respond({'error':'This workspace accepts localhost requests only.'},403)
            return False
        return True

    def do_GET(self):
        if not self.valid_host():
            return
        url = urlsplit(self.path)
        if url.path == '/api/recordings':
            with connect(self.database) as db:
                rows = db.execute('SELECT id,created,body FROM recordings ORDER BY created DESC').fetchall()
            records = []
            for identifier,created,body in rows:
                recording = json.loads(body)
                records.append({key:recording[key] for key in ('id','created','name','mode','duration_ms','sha256')})
            self.respond({'recordings':records,'version':__version__})
        elif url.path.startswith('/api/recordings/'):
            identifier = url.path.removeprefix('/api/recordings/')
            with connect(self.database) as db:
                row = db.execute('SELECT body FROM recordings WHERE id=?',(identifier,)).fetchone()
            if not row:
                self.respond({'error':'Recording not found.'},404)
                return
            recording = json.loads(row[0])
            if url.query == 'format=csv':
                self.respond(export_csv(recording),kind='text/csv; charset=utf-8',filename=f'edge-replay-{recording["id"]}.csv')
            else:
                self.respond(recording,filename=f'edge-replay-{recording["id"]}.json' if url.query == 'download=1' else None)
        elif url.path in ('/','/style.css','/app.js','/motion.js','/demo.csv','/example-can.csv','/favicon.svg'):
            super().do_GET()
        elif url.path.startswith('/vendor/') and url.path.removeprefix('/vendor/') in {p.name for p in (WEB/'vendor').iterdir()}:
            super().do_GET()
        else:
            self.respond({'error':'Not found.'},404)

    def do_POST(self):
        if not self.valid_host():
            return
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            self.respond({'error':'Cross-origin writes are not allowed.'},403)
            return
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                raise ValueError('Send application/json.')
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Request must be between 1 byte and 4 MiB.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError('Request must be a JSON object.')
            if urlsplit(self.path).path != '/api/recordings':
                self.respond({'error':'Not found.'},404)
                return
            recording = parse_trace(data.get('name'), data.get('csv'))
            recording.update(id=str(uuid.uuid4()), created=datetime.now(timezone.utc).isoformat(),version=__version__)
            with connect(self.database) as db:
                db.execute('INSERT INTO recordings VALUES (?,?,?)',(recording['id'],recording['created'],canonical_json(recording)))
            self.respond(recording,201)
        except (ValueError,TypeError,RecursionError,OverflowError) as error:
            self.respond({'error':str(error)},400)


def make_server(port=8766,database='edge-replay.sqlite3'):
    return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,database=str(database)))
