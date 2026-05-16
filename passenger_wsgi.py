import os
import sys
import asyncio
import io

# ============================================
# PASSENGER WSGI ENTRY POINT
# Custom ASGI-to-WSGI bridge (tanpa a2wsgi)
# a2wsgi TIDAK kompatibel dengan Phusion Passenger
# ============================================

PROJECT_ROOT = '/home/riaudevo/fastapi_app'
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
except ImportError:
    pass

from app.main import app as fastapi_app

# --- Database Init (uncomment kalau DB sudah siap di server) ---
# from app.database import create_db_and_tables
# create_db_and_tables()


def application(environ, start_response):
    try:
        scope = {
            'type': 'http',
            'asgi': {'version': '3.0'},
            'http_version': '1.1',
            'method': environ['REQUEST_METHOD'],
            'path': environ.get('PATH_INFO', '/'),
            'root_path': environ.get('SCRIPT_NAME', ''),
            'query_string': environ.get('QUERY_STRING', '').encode('latin-1'),
            'headers': [],
            'server': (
                environ.get('SERVER_NAME', 'localhost'),
                int(environ.get('SERVER_PORT', '80'))
            ),
        }

        for key, value in environ.items():
            if key.startswith('HTTP_'):
                name = key[5:].lower().replace('_', '-').encode()
                scope['headers'].append((name, value.encode()))
            elif key == 'CONTENT_TYPE':
                scope['headers'].append((b'content-type', value.encode()))
            elif key == 'CONTENT_LENGTH':
                scope['headers'].append((b'content-length', value.encode()))

        # --- Safe body reading ---
        # Passenger can pass invalid/missing CONTENT_LENGTH which causes
        # wsgi.input.read() to fail with "Negative size passed to PyBytes_FromStringAndSize".
        # Fix: explicitly read only CONTENT_LENGTH bytes.
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0) or 0)
        except (ValueError, TypeError):
            content_length = 0

        body_input = environ.get('wsgi.input')
        if body_input and content_length > 0:
            request_body = body_input.read(content_length)
        else:
            request_body = b''

        status_code = 500
        response_headers = []
        body_parts = []

        async def receive():
            return {'type': 'http.request', 'body': request_body, 'more_body': False}

        async def send(message):
            nonlocal status_code, response_headers
            if message['type'] == 'http.response.start':
                status_code = message['status']
                response_headers = [
                    (k.decode('latin-1'), v.decode('latin-1'))
                    for k, v in message.get('headers', [])
                ]
            elif message['type'] == 'http.response.body':
                body_parts.append(message.get('body', b''))

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fastapi_app(scope, receive, send))
        finally:
            loop.close()

        status_phrases = {
            200: 'OK', 201: 'Created', 204: 'No Content',
            301: 'Moved Permanently', 302: 'Found', 304: 'Not Modified',
            400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
            404: 'Not Found', 405: 'Method Not Allowed',
            422: 'Unprocessable Entity', 500: 'Internal Server Error',
        }
        phrase = status_phrases.get(status_code, 'Unknown')
        start_response(f'{status_code} {phrase}', response_headers)
        return body_parts

    except Exception as e:
        import traceback
        body = f"BRIDGE ERROR:\n{traceback.format_exc()}".encode()
        start_response('500 Internal Server Error', [
            ('Content-Type', 'text/plain'),
            ('Content-Length', str(len(body))),
        ])
        return [body]