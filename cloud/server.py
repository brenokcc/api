#!/usr/bin/env python
import os
import time
import json
import urllib.parse
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 9999

if os.path.exists('/Users/breno'):
    WORKDIR = '/Users/breno/cloud/'
    DOMAIN_NAME = 'local.aplicativo.click'
    NGINX_DEPLOY_DIR = '/usr/local/etc/nginx/servers'
    CERTIFICATE = ()
else:
    WORKDIR = '/opt/cloud/'
    DOMAIN_NAME = 'cloud.aplicativo.click'
    NGINX_DEPLOY_DIR = '/etc/nginx/conf.d'
    CERTIFICATE = (
        '/etc/letsencrypt/live/cloud.aplicativo.click/fullchain.pem',
        '/etc/letsencrypt/live/cloud.aplicativo.click/privkey.pem'
    )

def execute(cmd):
    print(cmd)
    os.system(cmd)

def start():
    ssl = 'listen 443 ssl; ssl_certificate %s; ssl_certificate_key %s; if ($scheme = http) {return 301 https://$server_name$request_uri;}' % CERTIFICATE if CERTIFICATE else ''
    conf = 'server {listen 80; server_name %s; location / { proxy_pass http://127.0.0.1:%s; } %s }' % (DOMAIN_NAME, PORT, ssl)
    execute("echo '{}' > {}/cloud.conf".format(conf, NGINX_DEPLOY_DIR))
    execute('nginx -s reload')

def stop(*args):
    execute("rm -f {}/cloud.conf".format(NGINX_DEPLOY_DIR))
    execute('nginx -s reload')


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        self._data = {}
        super().__init__(*args, **kwargs)

    def _get_code(self):
        if os.path.exists(self._get_project_dir()):
            execute('cd {} && git pull'.format(self._get_project_dir()))
        else:
            execute('git clone {} {}'.format(self._get_clone_url(), self._get_project_dir()))

    def _clear(self):
        for image_id in os.popen('docker images -f "dangling=true" -q').read().split():
            execute('docker rmi {}'.format(image_id))

    def deploy(self):
        self._get_code()
        execute('docker-compose -f {} up -d --build'.format(self._get_compose_file_path()))
        self._clear()
        execute("echo '{}' > {}/{}.conf".format(self._get_nginx_project_conf(), NGINX_DEPLOY_DIR, self._get_project_name()))
        execute('nginx -s reload')
        return self.get_project_deploy_url()

    def undeploy(self):
        execute("rm -rf {}/{}.conf".format(NGINX_DEPLOY_DIR, self._get_project_name()))
        execute('nginx -s reload')
        execute('docker-compose -f {} down'.format(self._get_compose_file_path()))
        execute('docker rmi {}_web'.format(self._get_project_name()))
        execute('docker rmi {}-web'.format(self._get_project_name()))
        return 'OK'

    def destroy(self):
        self.undeploy()
        execute('rm -rf {}'.format(self._get_project_dir()))
        return 'OK'

    def update(self):
        execute('cd {} && git pull'.format(self._get_project_dir()))
        execute('docker-compose -f {} up -d --force-recreate --no-deps web'.format(self._get_compose_file_path()))
        execute("echo '{}' > {}/{}.conf".format(self._get_nginx_project_conf(), NGINX_DEPLOY_DIR, self._get_project_name()))
        execute('nginx -s reload')
        return 'OK'

    def test(self):
        self._get_code()
        execute('docker-compose -f {} up --build --exit-code-from test'.format(self._get_compose_file_path(test=True)))
        return 'OK'

    def _get_project_name(self):
        return self._data.get('repository').split('/')[-1].split('.git')[0]

    def _get_project_dir(self):
        return os.path.join(WORKDIR, self._get_project_name())

    def _get_container_name(self):
        return '{}_web_1'.format(self._get_project_name())

    def _get_container_port(self):
        return os.popen('docker-compose -f {} port web 8000'.format(self._get_compose_file_path())).read().strip().split(':')[-1]

    def _get_compose_file_path(self, test=False):
        file_name = 'docker-compose.test.yml' if test else 'docker-compose.yml'
        return os.path.join(WORKDIR, self._get_project_name(), file_name)

    def _get_nginx_project_conf(self):
        ssl = 'listen 443 ssl; ssl_certificate %s; ssl_certificate_key %s; if ($scheme = http) {return 301 https://$server_name$request_uri;}' % CERTIFICATE if CERTIFICATE else ''
        static = ' '  or 'location /static { alias %s; }' % os.path.join(self._get_project_dir(), '.deploy', 'static')
        media = 'location /media { alias %s; }' % os.path.join(self._get_project_dir(), '.deploy', 'media')
        return 'server {listen 80; server_name %s.%s; location / { proxy_pass http://127.0.0.1:%s; } %s %s %s }' % (
            self._get_project_name(), DOMAIN_NAME, self._get_container_port(), ssl, static, media
        )

    def get_project_deploy_url(self):
        return 'http://{}.{}/'.format(self._get_project_name(), DOMAIN_NAME)

    def _get_clone_url(self):
        return self._data.get('repository').replace('git:', 'https:')

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        data = urllib.parse.parse_qs(self.path[2:])
        self.wfile.write('{}'.format(data).encode())

    def do_POST(self):
        self.send_response(200)
        self.end_headers()
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length'))).decode())
        tokens = []
        if os.path.exists(os.path.join(WORKDIR, 'tokens.txt')):
            tokens = open(os.path.join(WORKDIR, 'tokens.txt')).read().split('\n')
        print(data)
        if data.get('token') and data.get('token') in tokens:
            self._data.update(data)
            if data.get('action') == 'deploy':
                message = self.deploy()
            elif data.get('action') == 'update':
                message = self.update()
            elif data.get('action') == 'undeploy':
                message = self.undeploy()
            elif data.get('action') == 'destroy':
                message = self.destroy()
            elif data.get('action') == 'test':
                message = self.test()
            else:
                message = 'unknown action'
        else:
            message = 'not authorized'
        output = json.dumps(dict(message=message))
        with open(os.path.join(WORKDIR, 'server.log'), 'a') as file:
            file.write('<<< {}\n\n'.format(data))
            file.write('>>> {}\n\n'.format(output))
        self.wfile.write(output.encode())

signal.signal(signal.SIGTERM, stop)
httpd = HTTPServer(('127.0.0.1', PORT), SimpleHTTPRequestHandler)
try:
    start()
    print('Listening 127.0.0.1:{} ...'.format(PORT))
    httpd.serve_forever()
except KeyboardInterrupt:
    stop()
    print('Stopped!')



# curl -X POST http://localhost:9999 -d '{"action": "deploy", "project_name": "a1"}'
# curl -X POST http://localhost:9999 -d '{"action": "undeploy", "project_name": "a1"}'
