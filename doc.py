from django.conf import settings
from django.urls import path
from rest_framework import permissions

if 'drf_yasg' in settings.INSTALLED_APPS:
   from drf_yasg import openapi
   from drf_yasg import views
   from drf_yasg.inspectors import SwaggerAutoSchema
   from drf_yasg.utils import swagger_auto_schema

   parameter_mapping = dict(
      q_field=openapi.Parameter('q', openapi.IN_QUERY, description="Keywords used to execute the search.", type=openapi.TYPE_STRING),
      only_fields=openapi.Parameter('only', openapi.IN_QUERY, description="The name of the fields to be retrieved separated by comma (,).", type=openapi.TYPE_STRING),
      page=openapi.Parameter('page', openapi.IN_QUERY, description="Number of the page of the relation.", type=openapi.TYPE_STRING),
      page_size=openapi.Parameter('page_size', openapi.IN_QUERY, description="Number of items per page.", type=openapi.TYPE_INTEGER),
      relation_page=openapi.Parameter('relation_page', openapi.IN_QUERY, description="Number of the page of the relation.", type=openapi.TYPE_STRING),
      choices_field=openapi.Parameter('choices_field', openapi.IN_QUERY, description="Name of the field from which the choices will be displayed.", type=openapi.TYPE_STRING),
      choices_search=openapi.Parameter('choices_search', openapi.IN_QUERY, description="Term to be used in the choices search.", type=openapi.TYPE_STRING),
      subset_param=openapi.Parameter('subset', openapi.IN_QUERY, description="Name of the subset to be displayed", type=openapi.TYPE_STRING),
      id_parameter=openapi.Parameter('id', openapi.IN_PATH, description="The id of the object.", type=openapi.TYPE_INTEGER),
      ids_parameter=openapi.Parameter('ids', openapi.IN_PATH, description="The ids of the objects separated by comma (,).", type=openapi.TYPE_STRING),
   )
   def apidoc(**kwargs):
      def decorate(function):
         manual_parameters = [parameter_mapping[name] for name in kwargs.pop('parameters', ())]
         for name in kwargs.pop('filters', ()):
            name = 'userrole' if name.endswith('userrole') else name
            manual_parameters.append(
               openapi.Parameter(name, openapi.IN_QUERY, description=name, type=openapi.TYPE_STRING)
            )
         kwargs.update(manual_parameters=manual_parameters)
         return swagger_auto_schema(**kwargs)(function)
      return decorate

   schema_view = views.get_schema_view(
      openapi.Info(
         title="REST API",
         default_version='v1',
         description="Test description",
         terms_of_service="https://www.google.com/policies/terms/",
         contact=openapi.Contact(email="contact@snippets.local"),
         license=openapi.License(name="BSD License"),
      ),
      url=settings.SITE_URL,
      public=True,
      permission_classes=[permissions.AllowAny],
   )

   urlpatterns = [
       path('api/doc/', schema_view.with_ui('swagger', cache_timeout=0)),
   ]

   class AutoSchema(SwaggerAutoSchema):

      def get_tags(self, operation_keys=None):
         tags = self.overrides.get('tags', None)
         if not tags:
            model = getattr(self.view, 'model', None)
            if model:
               tags = [model.__name__.lower()]
         if not tags:
            tags = [operation_keys[0]]

         return tags

else:
   urlpatterns = []
   def apidoc(**kwargs):
      def decorate(function):
         return function
      return decorate

