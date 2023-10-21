from django.core.management.base import BaseCommand

from api.test.selenium import Browser


class Command(BaseCommand):

    def handle(self, *args, **options):
        browser = Browser('https://google.com', headless=False)
        browser.open('/')
        try:
            print('Use the object "browser" no navigate.')
            breakpoint()
        except KeyboardInterrupt:
            pass
        browser.close()

