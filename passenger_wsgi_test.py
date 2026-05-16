# ULTRA MINIMAL TEST - Tanpa FastAPI, tanpa import berat
# Rename file ini jadi passenger_wsgi.py di server

def application(environ, start_response):
    body = b'{"test": "PASSENGER HIDUP!"}'
    start_response('200 OK', [
        ('Content-Type', 'application/json'),
        ('Content-Length', str(len(body))),
    ])
    return [body]
