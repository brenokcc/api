from django.http import HttpResponse
from django.urls import re_path
from django.views.static import serve

INDEX_FILE_CONTENT = open(__file__.replace('middleware.py', 'static/app/index.html')).read()


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH";
        return response


class ReactJsMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_opt = request.method == 'OPTIONS'
        is_api = request.path.startswith('/api/v1/')
        is_json = request.META.get('HTTP_ACCEPT') == 'application/json'

        if is_api and not is_opt and not is_json:
            url = "{}://{}".format(request.scheme, request.get_host())
            response = HttpResponse(INDEX_FILE_CONTENT.replace(
                '<body>', f'<body><script>API_URL="{url}"</script>'
            ))
        else:
            response = self.get_response(request)
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
