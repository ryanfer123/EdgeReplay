"""Public configuration only. User authentication happens directly in the browser."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

TABLE = 'edge_replay_cloud_workspaces'
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


def cloud_config(environ=None, config_path=None):
    """Return safe browser config, or a disabled state without exposing bad values.

    Environment variables override a local, ignored cloud.config.json at repo root.
    Never configure a service-role or secret key here.
    """
    env = os.environ if environ is None else environ
    path = Path(config_path) if config_path is not None else Path(__file__).resolve().parent.parent / 'cloud.config.json'
    local = {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value, dict):
            local = value
    except (OSError, ValueError):
        pass
    url = env.get('SUPABASE_URL', local.get('SUPABASE_URL', ''))
    key = env.get('SUPABASE_PUBLISHABLE_KEY', local.get('SUPABASE_PUBLISHABLE_KEY', ''))
    disabled = {'configured': False, 'message': 'Cloud storage is not configured on this server.'}
    if not isinstance(url, str) or not isinstance(key, str):
        return disabled
    try:
        parsed = urlsplit(url)
        valid_url = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                     and not parsed.password and parsed.path in ('', '/')
                     and not parsed.query and not parsed.fragment and parsed.port in (None, 443)
                     and not any(char.isspace() for char in url))
    except ValueError:
        return disabled
    if not valid_url or not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', key):
        return disabled
    return {'configured': True, 'url': url.rstrip('/'), 'publishableKey': key,
            'table': TABLE, 'maxPayloadBytes': MAX_PAYLOAD_BYTES}
