from django.http import HttpResponse, HttpResponseRedirect
from django.urls import re_path
from django.conf import settings
from django.views.static import serve
from .specification import API


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH";
        response["Access-Control-Max-Age"] = "600"
        return response


class ReactJsMiddleware:

    INDEX_FILE_CONTENT = None
    ICON_URL = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if ReactJsMiddleware.INDEX_FILE_CONTENT is None:
            specification = API.instance()
            host_url = "{}://{}".format(request.META.get('X-Forwarded-Proto', request.scheme), request.get_host())
            replaces = [
                ('<!--', ''), ('-->', ''),
                ('http://localhost:8000', host_url),
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
        is_api = request.path == '/' or request.path.startswith('/api/v1/')
        is_json = request.META.get('HTTP_ACCEPT') == 'application/json'
        is_raw = 'raw' in request.GET

        if is_api and not is_opt and not is_json and not is_raw:
            response = HttpResponse(ReactJsMiddleware.INDEX_FILE_CONTENT)
        else:
            response = self.get_response(request)

        if request.path.endswith('/') and not is_opt:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
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
