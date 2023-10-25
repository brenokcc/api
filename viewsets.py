import json
import datetime
import requests
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_save, post_delete
from django.utils.autoreload import autoreload_started
from django.core.cache import cache
from drf_yasg import openapi
from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg.utils import swagger_auto_schema
from rest_framework import exceptions
from rest_framework import filters
from rest_framework import routers
from rest_framework import serializers, viewsets
from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.compat import coreapi, coreschema
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import permissions
from . import signals
from .models import Role
from .endpoints import ACTIONS, Endpoint, EndpointSet
from .serializers import *
from .specification import API
from .utils import to_snake_case, related_model, as_choices, to_choices


q_field = openapi.Parameter('q', openapi.IN_QUERY, description="Keywords used to execute the search.", type=openapi.TYPE_STRING)
only_fields = openapi.Parameter('only', openapi.IN_QUERY, description="The name of the fields to be retrieved separated by comma (,).", type=openapi.TYPE_STRING)
page = openapi.Parameter('page', openapi.IN_QUERY, description="Number of the page of the relation.", type=openapi.TYPE_STRING)
relation_page = openapi.Parameter('relation_page', openapi.IN_QUERY, description="Number of the page of the relation.", type=openapi.TYPE_STRING)
choices_field = openapi.Parameter('choices_field', openapi.IN_QUERY, description="Name of the field from which the choices will be displayed.", type=openapi.TYPE_STRING)
choices_search = openapi.Parameter('choices_search', openapi.IN_QUERY, description="Term to be used in the choices search.", type=openapi.TYPE_STRING)
subset_param = openapi.Parameter('subset', openapi.IN_QUERY, description="Name of the subset to be displayed", type=openapi.TYPE_STRING)
id_parameter = openapi.Parameter('id', openapi.IN_PATH, description="The id of the object.", type=openapi.TYPE_INTEGER)
ids_parameter = openapi.Parameter('ids', openapi.IN_PATH, description="The ids of the objects separated by comma (,).", type=openapi.TYPE_STRING)


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


class ObtainAuthToken(ObtainAuthToken):

    def oauth(self, code):
        specification = API.instance()
        for name, provider in specification.oauth.items():
            redirect_uri = "{}{}".format(self.request.META['HTTP_ORIGIN'], provider['redirect_uri'])
            access_token_request_data = dict(
                grant_type='authorization_code', code=code, redirect_uri=redirect_uri,
                client_id=provider['client_id'], client_secret=provider['client_secret']
            )
            response = requests.post(provider['access_token_url'], data=access_token_request_data, verify=False)
            if response.status_code != 200:
                print(redirect_uri)
                print('Logging with {} failed: {}'.format(name, response.text))
                break
                continue
            data = json.loads(response.text)
            headers = {
                'Authorization': 'Bearer {}'.format(data.get('access_token')),
                'x-api-key': provider['client_secret']
            }
            if provider.get('user_data_method', 'GET').upper() == 'POST':
                response = requests.post(provider['user_data_url'], data={'scope': data.get('scope')}, headers=headers)
            else:
                response = requests.get(provider['user_data_url'], data={'scope': data.get('scope')}, headers=headers)
            if response.status_code == 200:
                data = json.loads(response.text)
                username = data[provider['user_data']['username']]
                user = User.objects.filter(username=username).first()
                if user is None and provider.get('user_data').get('create'):
                    user = User.objects.create(
                        username=username,
                        email=data[provider['user_data']['email']] if provider['user_data']['mail'] else ''
                    )
                if user:
                    token = Token.objects.get_or_create(user=user)[0]
                    data = {'token': token.key}
                    self.update(token, data)
                    return Response(data)
                else:
                    message = 'Usuário "{}" inexistente.'.format(username)
                    return Response(dict(type='info', text=message))
        return Response(dict(type='info', text='Ocorreu um erro ao realizar login.'))


    def get(self, request, *args, **kwargs):
        code = self.request.GET.get('code')
        if code:
            return self.oauth(code)
        serializer = self.get_serializer()
        form = dict(type='form', method='post', name='login', action=request.path, fields=serialize_fields(serializer))
        return Response(form)

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        response['Access-Control-Expose-Headers'] = '*'
        if response.status_code == 200:
            token = Token.objects.get(key=response.data['token'])
        self.update(token, response.data)
        return response

    def update(self, token, data):
        user = dict(id=token.user.id, username=token.user.username, is_superuser=token.user.is_superuser)
        data.update(
            redirect='/api/v1/dashboard/', message='Autenticação realizada com sucesso.', user=user
        );


class Router(routers.DefaultRouter):
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        if specification.app:
            for prefix, viewset, basename in self.registry:
                if prefix and prefix != 'health':
                    urls.insert(0, path(f'{prefix}/add/'.format(prefix), viewset.as_view({'get': 'create', 'post': 'create'}), name=f'add-{prefix}'))
                    urls.insert(0, path(f'{prefix}/<int:pk>/edit/'.format(prefix), viewset.as_view({'get': 'update', 'put': 'update'}), name=f'edit-{prefix}'))
                    urls.insert(0, path(f'{prefix}/<int:pk>/delete/'.format(prefix), viewset.as_view({'get': 'destroy', 'delete': 'destroy'}), name=f'edit-{prefix}'))
        return urls


class ChoiceFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_fields(self, view):
        assert coreapi is not None, 'coreapi must be installed to use `get_schema_fields()`'
        assert coreschema is not None, 'coreschema must be installed to use `get_schema_fields()`'
        return [
            coreapi.Field(
                name='choices',
                required=False,
                location='query',
                schema=coreschema.String(
                    title='Name of the field',
                    description='Name of the field to display choices'
                )
            )
        ]

    def get_schema_operation_parameters(self, view):
        return [
            {
                'name': 'choices',
                'required': False,
                'in': 'query',
                'description': 'Name of the field',
                'schema': {
                    'type': 'string',
                },
            },
        ]


class FilterBackend(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        search = []
        filters = []
        if hasattr(view, 'context'):
            if 'only' in request.GET:
                filters = view.context['view'].item.relations.get(request.GET['only'], {}).get('filters')
                search = view.context['view'].item.relations.get(request.GET['only'], {}).get('search')
        else:
            filters = view.item.filters
            search = view.item.search
        return queryset.contextualize(request, dict(filters=filters, search=search))


class List(Endpoint):

    class Meta:
        target = 'queryset'

    @classmethod
    def get_qualified_name(cls):
        return 'list'

    def has_permission(self):
        return super().has_permission() or permissions.check_roles(self.context['view'].item.list_lookups, self.user, False)


class Add(Endpoint):
    class Meta:
        icon = 'plus'
        target = 'queryset'

    @classmethod
    def get_qualified_name(cls):
        return 'add'

    def has_permission(self):
        return super().has_permission() or permissions.check_roles(self.context['view'].item.add_lookups, self.user, False)


class Edit(Endpoint):

    class Meta:
        icon = 'pencil'

    @classmethod
    def get_qualified_name(cls):
        return 'edit'

    def has_permission(self):
        return super().has_permission() or permissions.check_roles(self.context['view'].item.edit_lookups, self.user, False)


class Delete(Endpoint):

    class Meta:
        icon = 'trash'

    @classmethod
    def get_qualified_name(cls):
        return 'delete'

    def has_permission(self):
        return super().has_permission() or permissions.check_roles(self.context['view'].item.delete_lookups, self.user, False)


class View(Endpoint):

    class Meta:
        icon = 'eye'
        modal = False

    @classmethod
    def get_qualified_name(cls):
        return 'view'

    def has_permission(self):
        item = specification.getitem(type(self.instance))
        return permissions.check_roles(item.view_lookups, self.user, False)


class Preview(View):

    class Meta:
        icon = 'eye'
        modal = True

    @classmethod
    def get_qualified_name(cls):
        return 'preview'


class ModelViewSet(viewsets.ModelViewSet):
    ACTIONS = {}
    SERIALIZERS = {}
    filter_backends = FilterBackend,
    pagination_class = PageNumberPagination
    serializer_class = DynamicFieldsModelSerializer
    permission_classes = AllowAny,

    def __init__(self, *args, **kwargs):
        self.queryset = self.get_queryset()
        self.fieldsets = kwargs.pop('fieldsets', ())
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        return self.model.objects.all().order_by('id')

    def apply_lookups(self, queryset):
        if self.request.user.is_superuser:
            lookups = None
        elif self.action == 'list':
            lookups = self.item.list_lookups
        elif self.action == 'retrieve':
            lookups = self.item.view_lookups

        if lookups:
            return permissions.apply_lookups(queryset, lookups, self.request.user)
        return queryset

    def get_serializer_class(self):
        if self.action in self.ACTIONS:
            return self.ACTIONS[self.action]
        else:
            _exclude = None
            _model = self.model
            key = '{}_{}'.format(self.action, self.model.__name__)
            cls = ModelViewSet.SERIALIZERS.get(key)
            if cls is None:
                if self.action == 'create':
                    if self.item.add_fieldsets:
                        _fields = []
                        for v in self.item.add_fieldsets.values():
                            _fields.extend(v)
                    else:
                        _fields = self.item.add_fields
                elif self.action == 'list':
                    _fields = self.item.list_display
                elif self.action == 'retrieve':
                    _fields = self.item.view_fields
                elif self.action == 'update' or self.action == 'partial_update':
                    if self.item.edit_fieldsets:
                        _fields = []
                        for v in self.item.edit_fieldsets.values():
                            _fields.extend(v)
                    else:
                        _fields = self.item.edit_fields
                elif self.action == 'destroy':
                    _fields = 'id',
                elif self.action in self.item.relations:
                    _exclude = self.item.relations[self.action]['related_field'],
                    _model = getattr(_model, self.action).field.remote_field.related_model
                else:
                    _fields = self.item.list_display
                class cls(DynamicFieldsModelSerializer):
                    class Meta:
                        ref_name = key
                        model = _model
                        if _exclude is None:
                            fields = _fields or '__all__'
                        else:
                            exclude = _exclude

                ModelViewSet.SERIALIZERS[key] = cls
            return cls

    def get_object(self):
        object = super().get_object()
        if self.action == 'retrieve':
            object._wrap = True
        return object

    @swagger_auto_schema(manual_parameters=[only_fields, page, subset_param])
    def retrieve(self, request, *args, **kwargs):
        permissions.check_roles(self.item.view_lookups, request.user)
        relation_name = request.GET.get('only')
        if relation_name:
            relation_name = self.get_serializer().get_real_field_name(relation_name)
        return self.choices_response(request, relation_name) or super().retrieve(request, *args, **kwargs)

    def filter_queryset(self, queryset):
        if self.action != 'retrieve':
            queryset = super().filter_queryset(queryset)
        if self.action == 'list' or self.action == 'retrieve':
            return self.apply_lookups(queryset)
        return queryset

    # auto_schema=None
    def list(self, request, *args, **kwargs):
        permissions.check_roles(self.item.list_lookups, request.user)
        return self.choices_response(request) or super().list(request, *args, **kwargs)

    def get_paginated_response(self, data):
        metadata = dict(actions= self.item.list_actions, search=self.item.search, filters=self.item.filters, subsets=self.item.list_subsets, aggregations=self.item.list_aggregations)
        return self.paginator.get_paginated_response(data, metadata, True)

    def create_form(self, request):
        if request.method == 'GET':
            serializer = self.get_serializer()
            name = '{}_{}'.format('Cadastrar', self.model._meta.verbose_name)
            form = dict(type='form', icon='plus', method='post', name=name, action=request.path, fields=serialize_fields(serializer, self.item.add_fieldsets))
            return Response(form)

    @swagger_auto_schema(manual_parameters=[choices_field, choices_search])
    def create(self, request, *args, **kwargs):
        permissions.check_roles(self.item.add_lookups, request.user)
        try:
            return self.choices_response(request) or self.create_form(request) or self.post_create(
                super().create(request, *args, **kwargs)
            )
        except ValidationError as e:
            return Response(dict(non_field_errors=e.message), status=status.HTTP_400_BAD_REQUEST)

    def post_create(self, response):
        response = Response({}) if specification.app else response
        response['USER_MESSAGE'] = 'Cadastro realizado com sucesso.'
        return response

    def perform_create(self, serializer):
        if False: #TODO performe check_lookups with self.item.add_lookups and serializer.validated_data
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        super().perform_create(serializer)

    def update_form(self, request):
        if request.method == 'GET':
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=instance.__dict__)
            serializer.is_valid()
            name = '{}_{}'.format('Editar', self.model._meta.verbose_name)
            form = dict(type='form', icon='pencil', method='put', name=name, action=request.path, fields=serialize_fields(serializer, self.item.edit_fieldsets))
            return Response(form)

    @swagger_auto_schema(manual_parameters=[choices_field, choices_search])
    def update(self, request, *args, **kwargs):
        permissions.check_roles(self.item.edit_lookups, request.user)
        return self.choices_response(request) or self.update_form(request) or self.post_update(
            super().update(request, *args, **kwargs)
        )

    def post_update(self, response):
        response = Response({}) if specification.app else response
        response['USER_MESSAGE'] = 'Atualização realizada com sucesso.'
        return response

    def perform_update(self, serializer):
        if False:  # TODO performe check_lookups with self.item.edit_lookups and serializer.validated_data
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        super().perform_update(serializer)

    def destroy_form(self, request):
        if request.method == 'GET':
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=instance.__dict__)
            serializer.is_valid()
            name = '{}_{}'.format('Editar', self.model._meta.verbose_name)
            form = dict(type='form', icon='trash', method='delete', name=name, action=request.path.replace('delete/', ''), fields=serialize_fields(serializer))
            return Response(form)

    @swagger_auto_schema(manual_parameters=[])
    def destroy(self, request, *args, **kwargs):
        permissions.check_roles(self.item.delete_lookups, request.user)
        return self.destroy_form(request) or self.post_destroy(super().destroy(request, *args, **kwargs))

    def post_destroy(self, response):
        response = Response({}) if specification.app else response
        response['USER_MESSAGE'] = 'Exclusão realizada com sucesso.'
        return response

    def perform_destroy(self, instance):
        if False:  # TODO performe check_lookups with self.item.delete_lookups and serializer.validated_data
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        super().perform_destroy(instance)

    def choices_response(self, request, relation_name=None):
        queryset = self.filter_queryset(self.get_queryset())
        if self.action in ('retrieve', 'update'):
            queryset = queryset.filter(pk=self.get_object().id)
        choices = to_choices(queryset, request, relation_name, limit_choices=self.action in ('list', 'retrieve'))
        return Response(choices) if choices is not None else None


class UserSerializer(serializers.Serializer):

    def to_representation(self, instance):
        if instance.is_authenticated:
            data = dict(
                id=self.instance.id,
                username=self.instance.username,
                roles=[
                    dict(id=role.id, name=role.get_description(), active=role.active)
                    for role in Role.objects.filter(username=instance.username)
                ]
            )
            return data
        return {}

    def has_permission(self):
        return True


class UserViewSet(viewsets.GenericViewSet):
    permission_classes = AllowAny,
    ACTIONS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_serializer_class(self):
        return ACTIONS.get(UserViewSet.ACTIONS.get(self.action), UserSerializer)

    def get_queryset(self):
        return apps.get_model('auth.user').objects.filter(pk=self.request.user.id)

    @swagger_auto_schema(manual_parameters=[only_fields])
    @action(detail=False, methods=["get"], url_path='user', url_name='user')
    def user(self, request, format=None):
        return Response(self.get_serializer(request.user).data, status=status.HTTP_200_OK)

    @classmethod
    def create_actions(cls):
        for serializer_cls in ACTIONS.values():
            if serializer_cls.get_target() == 'user':
                k = serializer_cls.get_api_name()
                methods = serializer_cls.get_api_methods()
                manual_parameters = [choices_field, choices_search] if serializer_cls._declared_fields else []
                function = create_action_view_func(serializer_cls)
                swagger_auto_schema(manual_parameters=manual_parameters)(function)
                action(detail=False, methods=methods, url_path=f'user/{k}', url_name=k, name=k)(function)
                setattr(cls, k, function)


class ActionViewSet(viewsets.GenericViewSet):

    ACTIONS = {}

    permission_classes = AllowAny,
    pagination_class = PageNumberPagination

    def get_serializer_class(self):
        return self.ACTIONS.get(self.action, serializers.Serializer)

    def get_queryset(self):
        return apps.get_model('auth.user').objects.filter(pk=self.request.user.id)

    @classmethod
    def create_actions(cls):
        for action_class in ACTIONS.values():
             if action_class.get_target() is None:
                k = action_class.get_api_name()
                methods = action_class.get_api_methods()
                manual_parameters = [choices_field, choices_search] if 'post' in methods else []
                function = create_action_view_func(action_class)
                swagger_auto_schema(tags=action_class.get_api_tags(), manual_parameters=manual_parameters)(function)
                action(detail=False, methods=methods, url_path=k, url_name=k, name=k)(function)
                setattr(cls, k, function)
                cls.ACTIONS[k] = action_class


class HealthViewSet(viewsets.GenericViewSet):
    serializer_class = serializers.Serializer
    permission_classes = AllowAny,
    http_method_names = ['get']

    def get_queryset(self):
        return User.objects.none()

    @swagger_auto_schema(tags=['health'])
    @action(detail=False, methods=["get"], url_path='check', url_name='check')
    def check(self, request):
        return Response({'status': 'UP', 'time': datetime.datetime.now().isoformat()}, status=status.HTTP_200_OK)


def model_view_set_factory(model_name):
    _model = apps.get_model(model_name)
    _item = specification.items[model_name]
    if not _item.filters:
        for field in model._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                _item.filters.append(field.name)
            elif isinstance(field, models.BooleanField):
                _item.filters.append(field.name)
            elif getattr(field, 'choices', None):
                _item.filters.append(field.name)
    if 'id' not in _item.filters:
        _item.filters.append('id')
    if not _item.search:
        for field in model._meta.get_fields():
            if isinstance(field, models.CharField):
                _item.search.append('{}__icontains'.format(field.name))
    class ViewSet(ModelViewSet):
        model = _model
        item = _item
        ordering_fields = item.ordering

        @swagger_auto_schema(manual_parameters=[q_field, only_fields, choices_field, choices_search, relation_page, subset_param] + [filter_param(name) for name in _item.filters])
        def list(self, *args, **kwargs):
            return super().list(*args, **kwargs)

    for qualified_name in item.actions:
        if qualified_name in ('add', 'view', 'edit', 'delete', 'list'): continue
        cls = ACTIONS[qualified_name]
        k = cls.get_api_name()
        url_path = k
        function = create_action_func(cls)
        method = 'post' if cls._declared_fields else 'get'
        methods = ['post', 'get'] if specification.app else [method]
        manual_parameters = [only_fields, choices_field, choices_search]
        if cls.get_target() == 'instances' or cls.get_target() == 'queryset':
            detail = False
            if cls.get_target() == 'instances':
                url_path = f'{k}/(?P<ids>[0-9,]+)'
                manual_parameters.append(ids_parameter)
        else:
            detail = True
            manual_parameters.append(id_parameter)
        swagger_auto_schema(manual_parameters=manual_parameters)(function)
        action(detail=detail, methods=['post', 'get'], url_path=url_path, url_name=k, name=k)(function)
        setattr(ViewSet, k, function)
        ViewSet.ACTIONS[k] = cls


    for k in item.relations:
        if item.relations[k].get('related_field'):
            function = create_relation_func(k, item.relations[k])
            manual_parameters = [only_fields]
            swagger_auto_schema(manual_parameters=manual_parameters)(function)
            action(detail=True, methods=['post', 'get'], url_path='{}/add'.format(k), url_name=k, name=k)(function)
            setattr(ViewSet, k, function)
        for qualified_name in item.relations[k].get('actions'):
            if qualified_name in ('add', 'view', 'edit', 'delete', 'list'): continue
            cls2 = ACTIONS[qualified_name]
            if cls2.get_target() == 'queryset':
                k2 = cls2.get_qualified_name()
                method = 'post' if cls2._declared_fields else 'get'
                methods = ['post', 'get'] if specification.app else [method]
                manual_parameters = [only_fields, choices_field, choices_search]
                function = create_action_func(cls2, item.relations[k]['name'])
                swagger_auto_schema(manual_parameters=manual_parameters)(function)
                action(detail=True, methods=['post', 'get'], url_path=k2, url_name=k2, name=k2)(function)
                setattr(ViewSet, k2, function)
                ViewSet.ACTIONS[k2] = cls2
    return ViewSet


def filter_param(name):
    return openapi.Parameter(name, openapi.IN_QUERY, description=name, type=openapi.TYPE_STRING)


def create_action_view_func(action_class):
    def func(self, request, *args, **kwargs):
        serializer = action_class(context=dict(request=request, view=self), instance=request.user)
        if not serializer.has_permission():
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        return serializer.to_response()

    func.__name__ = action_class.get_api_name()
    return func

def create_relation_func(func_name, relation):
    def func(self, request, **kwargs):
        instance = self.model.objects.get(pk=kwargs['pk'])
        serializer = self.get_serializer_class()(
            data=request.POST or None, context=dict(request=request, view=self)
        )

        choices = request.query_params.get('choices_field')
        if choices:
            term = request.query_params.get('choices_search')
            field = serializer.fields[choices]
            if isinstance(field, PaginableManyRelatedField):
                qs = field.child_relation.get_queryset()
            else:
                qs = field.queryset.all()
            return Response(as_choices(qs.apply_search(term)))

        if request.method == 'GET':
            serializer.is_valid()
            name = '{}_{}'.format('Adicionar', related_model(self.model, relation['name'])._meta.verbose_name)
            form = dict(type='form', method='post', name=name, action=request.path, fields=serialize_fields(serializer))
            return Response(form)

        if serializer.is_valid():
            serializer.validated_data[relation['related_field']] = instance
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    func.__name__ = func_name
    return func


def create_action_func(serializar_class, relation_name=None):
    def func(self, request, *args, **kwargs):
        if 'pk' in kwargs:
            source = getattr(
                self.model.objects.get(pk=kwargs['pk']), relation_name
            ) if relation_name else self.model.objects.get(pk=kwargs['pk'])
            if isfunction(source) or ismethod(source):
                source = source()
        elif 'ids' in kwargs:
            source = self.model.objects.filter(pk__in=kwargs['ids'].split(','))
        else:
            source = self.model.objects.all()
        serializer = serializar_class(context=dict(request=request, view=self), instance=source)
        if not serializer.has_permission():
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        return serializer.to_response()

    func.__name__ = serializar_class.get_api_name()
    return func


router = Router()
specification = API.instance()

for app_label in settings.INSTALLED_APPS:
    try:
        if app_label != 'api':
            __import__('{}.{}'.format(app_label, 'endpoints'), fromlist=app_label.split('.'))
    except ImportError as e:
        if not e.name.endswith('endpoints'):
            raise e
    except BaseException as e:
        raise e

for k, item in specification.items.items():
    model = apps.get_model(k)
    for name, relation in item.relations.items():
        if '.' not in name and relation['actions']:
            subitem = specification.getitem(related_model(model, name))
            for name in relation['actions']:
                subitem.actions.add(name)
    for name in item.list_actions:
        item.actions.add(name)
    for name in item.view_actions:
        item.actions.add(name)

for k, item in specification.items.items():
    model = apps.get_model(k)
    if item.roles:
        model = apps.get_model(k)
        model.__roles__ = item.roles
        post_save.connect(signals.post_save_func, model)
        post_delete.connect(signals.post_delete_func, model)
        for field in model._meta.many_to_many:
            m2m_changed.connect(signals.m2m_save_func, sender=getattr(model, field.name).through)
    router.register(item.prefix, model_view_set_factory(k), k)

UserViewSet.create_actions()
ActionViewSet.create_actions()

router.register('', UserViewSet, 'user')
router.register('', ActionViewSet, 'api')
router.register('health', HealthViewSet, 'check')


def api_watchdog(sender, **kwargs):
    sender.extra_files.add(Path('api.yml'))

autoreload_started.connect(api_watchdog)

