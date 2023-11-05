import os
from django.conf import settings
from rest_framework import permissions, urls
from django.contrib import admin
from django.urls import path, include, re_path

from rest_framework.authtoken import views
from django.views.generic import RedirectView
from .viewsets import router, ObtainAuthToken
from django.conf.urls.static import static
from api.middleware import ReactJsMiddleware
from . import doc


urlpatterns = [
    path('', RedirectView.as_view(url='/api/v1/login/', permanent=False)),
    path('api/v1/', include(router.urls)),
    path('api/v1/token/', ObtainAuthToken.as_view()),
    path('api/v1/login/', ObtainAuthToken.as_view()),
] + static('/media/', document_root=settings.MEDIA_ROOT) \
  + static('/static/', document_root=settings.STATIC_ROOT) \
  + ReactJsMiddleware.urlpatterns() \
  + doc.urlpatterns


