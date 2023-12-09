import json
from django.test import LiveServerTestCase
from django.contrib.auth.models import User
from django.core.management import call_command

BASE_URL = '/api/v1'

class ApiTestCase(LiveServerTestCase):

    def __init__(self, *args, **kwargs):
        self.headers = None
        self.logging = True
        super().__init__(*args, **kwargs)

    def loaddata(self, fixture_path):
        call_command('loaddata', '--skip-checks', '--verbosity', '0', fixture_path)

    def create_superuser(self, username='admin', password='123'):
        User.objects.create_superuser(username, password=password)

    def login(self, username, password):
        response = self.client.post(f'{BASE_URL}/api/login/', data=dict(username='admin', password='123'))
        data = response.json()
        self.headers = {'Authorization': 'Token {}'.format(data.get('token'))}

    def log(self, method, url, data, response):
        if self.logging:
            print('{}: {}'.format(method, url))
            try:
                if data:
                    print('Input:\n{}'.format(json.dumps(data, indent=4, ensure_ascii=False)))
                print('Output [{}]:\n{}'.format(response.status_code, json.dumps(response.json(), indent=4, ensure_ascii=False) if response.content else {}))
            except Exception:
                print(response.content)
                import traceback
                print(traceback.format_exc())
                print(data)
            print('\n')

    def request(self, method, url, data=None, status_code=None):
        url = f'{BASE_URL}{url}'
        func = getattr(self.client, method)
        response = func(url, data=data, headers=self.headers)
        self.log('GET', url, data, response)
        if status_code:
            self.assertEqual(status_code, response.status_code)
        return response.json() if response.content else None

    def get(self, url, data=None, status_code=None):
        return self.request('get', url, data=data, status_code=status_code)

    def post(self, url, data=None, status_code=None):
        return self.request('post', url, data=data, status_code=status_code)

    def put(self, url, data=None, status_code=None):
        return self.request('put', url, data=data, status_code=status_code)

    def patch(self, url, data=None, status_code=None):
        return self.request('patch', url, data=data, status_code=status_code)

    def delete(self, url, data=None, status_code=None):
        return self.request('delete', url, data=data, status_code=status_code)
