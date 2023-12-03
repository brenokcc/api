# -*- coding: utf-8 -*-
import os
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("aplication_name", nargs="*", type=str)

    def handle(self, *args, **options):
        application_name = options['aplication_name'][0]
        call_command('sync')
        call_command('gunicorn', application_name)
