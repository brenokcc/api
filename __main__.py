import sys
import os
from django.core.management import ManagementUtility


URLS_FILE_CONTENT = '''from django.urls import path, include

urlpatterns = [
    path('', include('api.urls')),
]
'''

MODELS_FILE_CONTENT = '''from django.db import models
'''

ACTIONS_FILE_CONTENT = '''from api import actions
'''

TASKS_FILE_CONTENT = '''from api.tasks import Task
'''

TEST_FILE_CONTENT = '''from api.test import SeleniumTestCase

"""
Tu run the tests, execute:
    python manage.py test
To run the tests in the browser, execute:
    python manage.py test --browser
To resume the execution from the fourth step for example, execute:
   python manage.py test --browser --from 2
To create development database from the fourth step for example, execute:
   python manage.py test --restore 4
To run the test as a tutorial, execute:
   python manage.py test --tutorial
"""

class TesteIntegracao(SeleniumTestCase):

    def test(self):
        self.create_superuser('admin', '123')

        if self.step():
            self.login('admin', '123')
            self.logout()

'''

LOCAL_SETTINGS_FILE_CONTENT = '''_DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': '?',
        'USER': 'postgres',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '5432'
    }
}'''


DEPLOY_WORKFLOW_CONTENT = '''name: DEPLOY

on:
  push:
    branches: [ "main", "master" ]
  workflow_dispatch:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy
        env:
          TOKEN: ${{ secrets.TOKEN }}
        run: |
          curl -X POST https://deploy.cloud.aplicativo.click/ -d '{"action": "deploy", "repository": "${{ github.repositoryUrl }}", "token": "${{ secrets.TOKEN }}"}'

'''

DOCKER_FILE_CONTENT = '''FROM yml-api
WORKDIR /opt/app
EXPOSE 8000
ADD . .
ENTRYPOINT ["python", "manage.py", "startserver", "{}"]

FROM yml-api-test as test
WORKDIR /opt/app
ADD . .
ENTRYPOINT ["python", "manage.py", "test"]
'''

DOCKER_COMPOSE_FILE_CONTENT = '''version: '3.9'

services:
  web:
    ports:
      - "8000"
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    volumes:
      - .docker/media:/opt/app/media
      - ./static:/opt/app/static
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      REDIS_HOST: redis
      POSTGRES_HOST: postgres
      WEASYPRINT_HOST: weasyprint
  redis:
    image: redis
    hostname: redis
    restart: always
    ports:
      - "6379"
    command: redis-server --loglevel warning
    volumes:
      - .docker/redis:/data
  postgres:
    image: postgres
    hostname: postgres
    environment:
      POSTGRES_DB: ${DATABASE_NAME:-database}
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD:-password}
    ports:
      - "5432"
    volumes:
      - .docker/postgres:/var/lib/postgresql/data
    healthcheck:
      test: psql -U postgres -d $$POSTGRES_DB -c "SELECT version();"
  weasyprint:
    image: weasyprint
    hostname: weasyprint
    ports:
      - "8888"
'''

DOCKER_COMPOSE_TEST_FILE_CONTENT = '''version: '3.9'
services:
  redis:
    image: redis
    hostname: redis
    restart: always
    ports:
      - "6379"
    command: redis-server --loglevel warning
    healthcheck:
      test: redis-server --version
  test:
    depends_on:
      redis:
        condition: service_healthy
    build:
      context: .
      dockerfile: Dockerfile
      target: test
'''

DOCKER_IGNORE_FILE_CONTENT = '''.docker
.github
.git
.gitignore
.dockerignore
.deploy
docker-compose.yml
Dockerfile
static
media
*.pyc
*.sqlite3
*.md
local_settings.py
.steps/
geckodriver.log
'''

REQUIREMENTS = '''yml-api
'''

I18N_YML = '''api:
All: Tudo
Add: Cadastrar
Filter: Filtrar
Delete: Excluir
View: Visualizar
Edit: Editar
Groups: Grupos
First Name: Primeiro Nome
'''

API_YML = '''api:
  app: true
  lang: pt-br
  title: Sloth Framework
  subtitle: Take your time!
  icon: /static/images/sloth2.svg
  logo: /static/images/sloth.svg
  footer:
    logo: /static/images/sloth2.svg
    version: 1.0.1
  theme:
    primary: 1351b4
    secondary: 071e41
    auxiliary: 2670e8
    highlight: 0c326f
    info: d4e5ff
    success: 1351b4
    warning: fff5c2
    danger: e52207
  index:
  dashboard:
  groups:
    adm: Administrador
  models:
    auth.user:
      prefix: users
      icon: user-pen
      search: username
      filters: date_joined__gte, is_superuser, username
      ordering: username
      actions: list, add, view, edit, delete, api.actions.changepassword, api.actions.changepasswords, api.actions.verifypassword
      fieldsets:
        dados_gerais: username, first_name, last_name, get_full_name
        dados_acesso: date_joined, is_staff, is_active
        contato: email
      relations:
        api.actions.userroles:
          fields: id, name, scope, model, value, active
          actions: view
      endpoints:
        add:
          fields: first_name, last_name, username
        list:
          fields: id, dados_gerais, dados_acesso
          actions: add, view, edit, delete, api.actions.changepassword, api.actions.changepasswords
          extends:
            active:
              fields: id, username
            inactive:
        view:
          fields: id, dados_gerais, dados_acesso, api.actions.userroles
          actions: api.actions.verifypassword, api.actions.changepassword
    api.role:
      prefix: roles
      endpoints:
        list:
          fields: id, name
          actions: view, edit
'''

def startproject():
    name = os.path.basename(os.path.abspath('.'))
    ManagementUtility(['django-admin.py', 'startproject', name, '.']).execute()
    settings_path = os.path.join(name, 'settings.py')
    settings_content = open(settings_path).read().replace(
        "'django.contrib.admin'",
        "'api', '{}', 'rest_framework', 'rest_framework.authtoken', 'drf_yasg'".format(name)
    ).replace('from pathlib', 'import os\nfrom pathlib')
    settings_content = settings_content.replace("'db.sqlite3'", "'db.sqlite3', 'TEST': {'NAME': 'test.sqlite3'}")
    # settings_append = open(settings.__file__).read().replace('import os', '').replace('# ', '')
    settings_append = 'from api.conf import *'
    with open(settings_path, 'w') as file:
        file.write('{}\n{}\n'.format(settings_content, settings_append))
    local_settings_path = os.path.join(name, 'local_settings.py')
    with open(local_settings_path, 'w') as file:
        file.write(LOCAL_SETTINGS_FILE_CONTENT.replace('?', name))
    urls_path = os.path.join(name, 'urls.py')
    with open(urls_path, 'w') as file:
        file.write(URLS_FILE_CONTENT)
    models_path = os.path.join(name, 'models.py')
    with open(models_path, 'w') as file:
        file.write(MODELS_FILE_CONTENT)
    actions_path = os.path.join(name, 'actions.py')
    with open(actions_path, 'w') as file:
        file.write(ACTIONS_FILE_CONTENT)
    tasks_path = os.path.join(name, 'tasks.py')
    with open(tasks_path, 'w') as file:
        file.write(TASKS_FILE_CONTENT)
    test_path = os.path.join(name, 'tests.py')
    with open(test_path, 'w') as file:
        file.write(TEST_FILE_CONTENT)

    api_yml_path = 'api.yml'
    with open(api_yml_path, 'w') as file:
        file.write(API_YML)

    i18n_yml_path = 'i18n.yml'
    with open(i18n_yml_path, 'w') as file:
        file.write(I18N_YML)

    workflows_path = os.path.join('.github', 'workflows')
    os.makedirs(workflows_path, exist_ok=True)
    deploy_workflow_path = os.path.join(workflows_path, 'deploy.yml')
    with open(deploy_workflow_path, 'w') as file:
        file.write(DEPLOY_WORKFLOW_CONTENT)
    ignore = ['bin/server.log', '.idea/', 'db.sqlite3', '*.pyc', '.DS_Store', 'geckodriver.log', '.docker', 'media', 'local_settings.py']
    if os.path.exists('.gitignore'):
        with open('.gitignore', 'a') as file:
            file.write('\n'.join(ignore))
    else:
        with open('.gitignore', 'w') as file:
            file.write('\n'.join(ignore))
    with open('Dockerfile', 'w') as file:
        file.write(DOCKER_FILE_CONTENT.format(name))
    with open('docker-compose.yml', 'w') as file:
        file.write(DOCKER_COMPOSE_FILE_CONTENT)
    with open('docker-compose.test.yml', 'w') as file:
        file.write(DOCKER_COMPOSE_TEST_FILE_CONTENT)
    with open('.dockerignore', 'w') as file:
        file.write(DOCKER_IGNORE_FILE_CONTENT)
    with open('requirements.txt', 'w') as file:
        file.write(REQUIREMENTS)


if __name__ == "__main__":
    path = os.path.dirname(__file__)
    if len(sys.argv) == 1:
        startproject()
        os.system('python3 manage.py sync')
    if len(sys.argv) == 2:
        if sys.argv[1] == 'clear':
            for image_id in os.popen('docker images -f "dangling=true" -q').read().split():
                os.system('docker rmi {}'.format(image_id))
        elif sys.argv[1] == 'build':
            os.system('docker build --target yml-api-src -t yml-api {}'.format(path))
            os.system('docker build --target yml-api-test -t yml-api-test {}'.format(path))
            os.system('docker build --platform linux/x86_64 --target yml-api-weasyprint -t weasyprint {}'.format(path))
        elif sys.argv[1] == 'up':
            os.system('docker-compose up --build')
        elif sys.argv[1] == 'log' or sys.argv[1] == 'logs':
            os.system('docker-compose logs --tail 20 -f')
        elif sys.argv[1] == 'down':
            os.system('docker-compose down')
        elif sys.argv[1] == 'test':
            os.system('docker-compose -f docker-compose.test.yml up --build --exit-code-from test')
            os.system('docker-compose -f docker-compose.test.yml down')
        elif sys.argv[1] == 'dockerhub':
            os.system('docker tag yml-api brenokcc/yml-api')
            os.system('docker login -u brenokcc -p {}'.format(os.environ.get('DOCKERHUB_PASSWORD')))
            os.system('docker push brenokcc/yml-api')
        elif sys.argv[1] == 'cloud':
            os.system('python3 {}'.format(os.path.join(path, 'cloud', 'server.py')))
