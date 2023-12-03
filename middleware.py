from django.http import HttpResponse, HttpResponseRedirect
from django.urls import re_path
from django.conf import settings
from django.views.static import serve
from uuid import uuid1
from .specification import API


def add_cors_headers(response):
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH";
    response["Access-Control-Max-Age"] = "600"
    return response


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS':
            return add_cors_headers(HttpResponse())
        return add_cors_headers(self.get_response(request))


class ReactJsMiddleware:

    INDEX_FILE_CONTENT = None
    ICON_URL = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS':
            return add_cors_headers(HttpResponse())

        if ReactJsMiddleware.INDEX_FILE_CONTENT is None:
            specification = API.instance()
            host_url = "{}://{}".format(request.META.get('X-Forwarded-Proto', request.scheme), request.get_host())
            replaces = [
                ('<!--', ''), ('-->', ''),
                ('http://localhost:8000', host_url),
                ('90b273be7c8711eeb74b2a8c307b6d2d', uuid1().hex),
                ('/static/images/icon.png', specification.icon)
            ]
            ReactJsMiddleware.ICON_URL = specification.icon
            ReactJsMiddleware.INDEX_FILE_CONTENT = open(
                __file__.replace('middleware.py', 'static/app/index.html')
            ).read()
            for a, b in replaces:
                ReactJsMiddleware.INDEX_FILE_CONTENT = ReactJsMiddleware.INDEX_FILE_CONTENT.replace(a, b)

        if request.path in ('/favicon.ico' , '/apple-touch-icon-120x120-precomposed.png', '/apple-touch-icon-120x120.png', '/apple-touch-icon.png', '/apple-touch-icon.png', '/apple-touch-icon-precomposed.png'):
            return HttpResponseRedirect(ReactJsMiddleware.ICON_URL)

        is_opt = request.method == 'OPTIONS'
        is_api = request.path == '/' or request.path.startswith('/api/v1/') or request.path == '/app/login/govbr/'
        is_json = request.META.get('HTTP_ACCEPT') == 'application/json'
        is_raw = 'raw' in request.GET
        if is_api and not is_json and not is_raw and not is_opt:
            response = HttpResponse(ReactJsMiddleware.INDEX_FILE_CONTENT)
        else:
            response = self.get_response(request)

        if request.path.endswith('/'):
            response["Vary"] = "Accept"
            response["Cache-Control"] = "max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            add_cors_headers(response)
        else:
            response['Content-Security-Policy'] = "frame-ancestors 'self' *"
            response["X-Frame-Options"] = "allowall"
        return response

    @staticmethod
    def view(request, path=None):
        document_root = __file__.replace(__file__.split('/')[-1], 'static/app')
        return serve(request, request.path, document_root=document_root)

    @staticmethod
    def urlpatterns():
        return [
            re_path(r"^(assets|css|images|js|webfonts|vite.svg|index.html)/(?P<path>.*)$", ReactJsMiddleware.view),
        ]
