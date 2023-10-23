import os
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


OPTIONS = 'deploy', 'update', 'backup', 'undeploy', 'destroy', 'test'
CLOUD_PROVIDER_API_URL = getattr(settings, 'CLOUD_API_URL', 'https://cloud.aplicativo.click/')
CLOUD_PROVIDER_API_TOKEN = getattr(settings, 'CLOUD_API_TOKEN', '0123456789')


class Command(BaseCommand):
    def add_arguments(self, parser):
        for option in OPTIONS:
            parser.add_argument('--{}'.format(option), nargs='*', help='Executes {}'.format(option))

    def handle(self, *args, **options):
        repository = open('.git/config').read().split('git@github.com:')[-1].split('.git')[0]
        repository = os.popen('git config --get remote.origin.url').read().strip()
        if repository.startswith('git@'):
            # git@domain:x/y.git --> https://domain/x/y.git
            repository = repository.replace(':', '/').replace('git@', 'https://')
        print(CLOUD_PROVIDER_API_URL)
        for action in OPTIONS:
            if options[action] is not None:
                break
        if action:
            data = dict(action=action, repository=repository, token=CLOUD_PROVIDER_API_TOKEN)
            if action == 'test':
                data.update(branch=os.popen('git rev-parse --abbrev-ref HEAD').read().strip())
            print('>>>', data)
            response = requests.post(CLOUD_PROVIDER_API_URL, json=data, timeout=600)
            print(response.text)
            print('<<<', response.json())
