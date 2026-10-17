"""Validate proxies in disposable Docker containers without Aiven or real credentials."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


MOCK_API = '''import json
from http.server import HTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(401)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"detail":"Invalid email or password"}')
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ready",
            "proto": self.headers.get("X-Forwarded-Proto"),
            "client": self.headers.get("X-Forwarded-For")}).encode())
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
'''


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def request(url):
    body = b'{"email":"fake@example.test","password":"not-real"}' if 'login' in url else None
    # Try to evade the limiter by forging a different internal IP on every request.
    req = Request(url, data=body, headers={
        'Content-Type': 'application/json', 'X-Pelifolk-Client': uuid4().hex,
    })
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, dict(response.headers), response.read().decode()


def main():
    root = Path(__file__).resolve().parents[1]
    name = 'pelifolk-deploy-check-' + uuid4().hex[:8]
    containers = []
    with tempfile.TemporaryDirectory(prefix='pelifolk-proxy-static-') as folder:
        static = Path(folder)
        static.chmod(0o755)  # Nginx workers must be able to read the fake frontend.
        (static / 'index.html').write_text('<html><app-root>Deployment validation</app-root></html>')
        try:
            docker('network', 'create', name)
            services = [
                ('api', ['--network-alias', 'api', 'python:3.11-slim', 'python', '-c', MOCK_API]),
                ('web', ['--network-alias', 'web',
                         '-v', f'{root}/deploy/nginx.conf:/etc/nginx/nginx.conf:ro',
                         '-v', f'{static}:/usr/share/nginx/html:ro', 'nginx:alpine']),
                ('https', ['-p', '127.0.0.1::8080', '-e', 'PELIFOLK_DOMAIN=http://:8080',
                           '-e', 'ACME_EMAIL=fake@example.com',
                           '-v', f'{root}/deploy/Caddyfile:/etc/caddy/Caddyfile:ro', 'caddy:2-alpine']),
            ]
            for label, args in services:
                container = name + '-' + label
                containers.append(container)
                docker('run', '-d', '--name', container, '--network', name, *args)
            info = json.loads(docker('inspect', containers[-1]))[0]
            port = info['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort']
            origin = 'http://127.0.0.1:' + port
            for _ in range(30):
                try:
                    if request(origin + '/health/ready')[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(.2)
            ready = request(origin + '/health/ready')
            assert ready[0] == 200
            forwarding = json.loads(ready[2])
            assert forwarding['proto'] == 'https'
            assert forwarding['client'] and len(forwarding['client']) != 32
            assert '<app-root' in request(origin + '/users')[2], 'SPA fallback failed'
            responses = [request(origin + '/api/v1/auth/login') for _ in range(12)]
            codes = [response[0] for response in responses]
            assert 401 in codes and 429 in codes, codes
            limited = next(response for response in responses if response[0] == 429)
            assert limited[1].get('Retry-After') == '12', limited
            assert 'no-store' in limited[1].get('Cache-Control', ''), limited
            assert json.loads(limited[2])['detail'].startswith('Too many')
            print(json.dumps({'login_statuses': codes, 'spoofed_header_cannot_bypass': True,
                              'ready': 200, 'spa_fallback': 200}))
            # Validate HTTPS configuration offline, without requesting certificates.
            docker('run', '--rm', '--network', 'none',
                   '-e', 'PELIFOLK_DOMAIN=ranch.example.com', '-e', 'ACME_EMAIL=fake@example.com',
                   '-v', f'{root}/deploy/Caddyfile:/etc/caddy/Caddyfile:ro',
                   'caddy:2-alpine', 'caddy', 'adapt', '--config', '/etc/caddy/Caddyfile', '--validate')
            print('HTTPS configuration syntax: valid (no certificate requested)')
        finally:
            for container in reversed(containers):
                subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
            subprocess.run(['docker', 'network', 'rm', name], capture_output=True)


if __name__ == '__main__':
    main()
