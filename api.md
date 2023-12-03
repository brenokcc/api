# API

## apy.yml
- app
    - :bol
- lang
    - :str
- title
    - :str
- subtitle
    - :str
- icon
    - :str
- logo
    - :str
- footer
    - logo:
        - :str
    - version
        - :str
- oauth
    - < name >
        - client_id
            - :str
        - client_secret
            - :str
        - redirect_uri
            - :str
        - authorize_url
            - :str
        - access_token_url
            - :str
        - user_data_url
            - :str
        - user_logout_url
            - :str
        - user_scope
            - :str
        - user_data
            - username
                - :str
            - email
                - :str
            - create
                - :bool
- theme
    - primary
    - secondary
    - auxiliary
    - highlight
    - info
    - success
    - warning
    - danger
    - radius
- groups
    - < name >
        - < verbose_name >
- models:
    - < app >.< model >
        - prefix
            - :str
        - icon
            - :str
        - search
            - :str_list
        - endpoints
            - list
                - :str
                - {...}
                    - fields
                        - :str_list
                    - fieldsets
                        - < name >
                            - :str_list
                    - actions
                        - :str_list
                    - subsets
                        - :str_list
                            - < name >
                                - :null
                            - {...}
                                - fields
                                    - :str_list
                                - fieldsets
                                    - < name >
                                        - :str_list
                                - actions
                                    - :str_list
            - add
                - :str_list
                - {...}
                    - OR
                        - fields:
                            - :str_list
                        - fieldsets
                            - < name >
                                - :str_list
                                - {...}
                                    - fields
                                        - :str_list
                                    - requires
                                        - :str_list
                                        - < role >
                                            - :null
                                            - < scope >
                                                - :str
            - edit
                - :str_list
                - {...}
                    - OR
                        - fields:
                            - :str_list
                        - fieldsets
                            - < name >
                                - :str_list
                                - {...}
                                    - fields
                                        - :str_list
                                    - requires
                                        - :str_list
                                        - < role >
                                            - :null
                                            - < scope >
                                                - :str
            - view
                - :str_list
                - {...}
                    - actions
                        - :str_list
                    - OR
                        - fields
                            - :str_list
                        - fieldsets
                            - < name >
                                - :str_list
                                - {...}
                                    - fields
                                        - :str_list
                                    - requires
                                        - :str_list
                                        - < role >
                                            - :null
                                            - < scope >
                                                - :str
            - delete
                - null
                - OR
                    - fields
                        - :str_list
                    - fieldsets
                        - < name >
                            - :str_list

## UI

### widgets

- CPF
- CNPJ
- Telefone
- Cor
- CEP

## Cloud

### Client

- python manage.py
    - deploy
    - update
    - undeploy
    - destroy
- environment
    - CLOUD_API_TOKEN

### Server

## Code

### api

- components
    - components
        - Image
        - Link
        - QrCode
        - Progress
        - Status
        - Badge
        - Indicators
        - Boxes
        - Info
        - Warning
        - Table
        - TemplateContent
        - Banner
        - Map
- endpoints
    - Endpoint
        - Meta
            - icon
                - :str
            - modal
                - :str
            - title
                - :str
            - target
                - :enum
                    - instance
                    - instances
                    - queryset
                    - user
        - get()
        - post()
        - check_permission()
    - EndpointSet
        - endpoints
            - :list
    - CharField
    - BooleanField
    - IntegerField
    - DateField
    - FileField
    - DecimalField
    - EmailField
    - HiddenField

## Project

### Setup


### Creation

- File System
    1) mkdir \<name>
    2) python -m api
- Repository
    1) git clone \<url>
    2) cd \<directory>
    2) python -m api

### Structure
- .gitignore
- \<app>
    - models.py
    - endpoints.py
    - settings.py
    - tasks.py
    - urls.py
    - wsgi.py
- api.yml
- Dockerfile
- docker-compose.yml
- docker-compose.test.yml
- requirements.txt
- manage.py


### Development
- Coding
- python manage.py
    - sync
    - runserver

### Testing
- Local
    - python manage.py test
- Docker
    - docker-compose -f docker-compose.yml up

### Versioning
- git
    - pull origin master
    - checkout -b \<branch>
    - add .
    - commit -am '\<message>'
    - push origin \<branch>
