from django.core.cache import cache
from rest_framework.authentication import TokenAuthentication


class CachedTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        credentials = cache.get(key, None)
        if credentials:
            return credentials
        credentials = super().authenticate_credentials(key)
        cache.set(key, credentials)
        return credentials
