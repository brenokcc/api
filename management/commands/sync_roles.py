# -*- coding: utf-8 -*-
from django.conf import settings
from django.apps import apps
from api.specification import API
from api.models import Role
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        Role.objects.all().delete()
        for k, item in API.instance().items.items():
            if item.roles:
                model = apps.get_model(k)
                for obj in model.objects.all():
                    print(obj)
                    obj.save()
