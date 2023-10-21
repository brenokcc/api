# API

## Development

### Install

> pip install yml-api

### Create Project

> mkdir $project_name
> 
> cd $project_name
> 
> python -m api

### Sync Project

> python manage.py sync

### Run Project

> python manage.py runserver

### Test Project

> python manage.py test

## Deploy

Before deploying the application in a server running the Cloud API, it is necessary to configure the follwing
environment variables:

CLOUD_API_URL=https://cloud.aplicativo.click/

CLOUD_API_TOKEN=0123456789

### Deploy Project

> python manage.py cloud --deploy

### Update Project

> python manage.py cloud --update

### Destroy Project

> python manage.py cloud --destroy


## Docker

### Image Creation

> python -m api build

### Run Project

> python -m api up

### Project Log

> python -m api log

### Stop Log

> python -m api down

### Test Project

> python -m api test