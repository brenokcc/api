import os
from django.conf import settings
from rest_framework import permissions, urls
from django.contrib import admin
from django.urls import path, include, re_path

from rest_framework.authtoken import views
from django.views.generic import RedirectView
from .viewsets import router
from django.conf.urls.static import static
from api.middleware import ReactJsMiddleware
from . import doc


urlpatterns = [
    path('', RedirectView.as_view(url='/api/login/', permanent=False)),
    path('api/', include(router.urls)),
] + static('/api/media/', document_root=settings.MEDIA_ROOT) \
  + static('/api/static/', document_root=settings.STATIC_ROOT) \
  + ReactJsMiddleware.urlpatterns() \
  + doc.urlpatterns


