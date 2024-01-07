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
from rest_framework import exceptions
from rest_framework import filters
from rest_framework import routers
from rest_framework import serializers, viewsets
from rest_framework import status

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
from .doc import apidoc


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

    def check_permission(self):
        return super().check_permission() or permissions.check_roles(self.context['view'].item.list_lookups, self.user, False)


class Add(Endpoint):
    class Meta:
        icon = 'plus'
        target = 'queryset'

    @classmethod
    def get_qualified_name(cls):
        return 'add'

    def check_permission(self):
        return super().check_permission() or permissions.check_roles(self.context['view'].item.add_lookups, self.user, False)


class Edit(Endpoint):

    class Meta:
        icon = 'pencil'
        target = 'instance'

    @classmethod
    def get_qualified_name(cls):
        return 'edit'

    def check_permission(self):
        return super().check_permission() or permissions.check_roles(self.context['view'].item.edit_lookups, self.user, False)


class Delete(Endpoint):

    class Meta:
        icon = 'trash'
        target = 'instance'

    @classmethod
    def get_qualified_name(cls):
        return 'delete'

    def check_permission(self):
        return super().check_permission() or permissions.check_roles(self.context['view'].item.delete_lookups, self.user, False)


class View(Endpoint):

    class Meta:
        icon = 'eye'
        modal = False
        target = 'instance'

    @classmethod
    def get_qualified_name(cls):
        return 'view'

    def check_permission(self):
        item = specification.getitem(type(self.instance))
        return permissions.check_roles(item.view_lookups, self.user, False)


class Preview(View):

    class Meta:
        icon = 'eye'
        modal = True
        target = 'instance'

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
                    _fields = []
                    for fieldset in self.item.add_fieldsets.values():
                        if fieldset.get('requires'):
                            if not permissions.check_roles(fieldset.get('requires'), self.request.user, False):
                                continue
                        _fields.extend(fieldset['fields'].keys())
                elif self.action == 'list':
                    _fields = self.item.list_display
                elif self.action == 'retrieve':
                    _fields = [k[4:] if k.startswith('get_') else k for k in self.item.view_fields.keys()]
                    if _fields and 'id' not in _fields:
                        _fields.insert(0, 'id')
                elif self.action == 'update' or self.action == 'partial_update':
                    _fields = []
                    _fieldsets = self.item.related_fieldsets.get(self.request.GET.get('rel')) or self.item.edit_fieldsets or self.item.add_fieldsets
                    for fieldset in _fieldsets.values():
                        if fieldset.get('requires'):
                            if not permissions.check_roles(fieldset.get('requires'), self.request.user, False):
                                continue
                        _fields.extend(fieldset['fields'].keys())
                elif self.action == 'destroy':
                    _fields = 'id',
                elif self.action in self.item.relations:
                    if 'fieldsets' in self.item.relations[self.action]:
                        _fields = []
                        for fieldset in self.item.relations[self.action]['fieldsets'].values():
                            _fields.extend(fieldset['fields'].keys())
                    elif len(self.item.relations[self.action]['fields'])>1:
                        _fields = [k[4:] if k.startswith('get_') else k for k in self.item.relations[self.action]['fields']]
                    else:
                        _exclude = self.item.relations[self.action]['related_field'],
                    attr = getattr(_model(pk=0), self.action)
                    _model = attr.model if hasattr(attr, 'model') else attr().model
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

    @apidoc(parameters=['only_fields', 'page', 'page_size', 'subset_param'])
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
            form = dict(type='form', icon='plus', method='post', name=name, action=request.path, fields=serialize_fields(serializer, self.item.add_fieldsets, request))
            return Response(form)

    @apidoc(parameters=['choices_field', 'choices_search'])
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
            _fieldsets = self.item.related_fieldsets.get(self.request.GET.get('rel')) or self.item.edit_fieldsets or self.item.add_fieldsets
            form = dict(type='form', icon='pencil', method='put', name=name, action=request.path, fields=serialize_fields(serializer, _fieldsets, request))
            return Response(form)

    @apidoc(parameters=['choices_field', 'choices_search'])
    def update(self, request, *args, **kwargs):
        rel = self.request.GET.get('rel')
        item = specification.getitem(type(getattr(self.get_object(), rel))) if rel else self.item
        permissions.check_roles(item.edit_lookups, request.user)
        try:
            return self.choices_response(request) or self.update_form(request) or self.post_update(
                super().update(request, *args, **kwargs)
            )
        except ValidationError as e:
            return Response({'non_field_errors': e.message}, status=status.HTTP_400_BAD_REQUEST)

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
            name = '{}_{}'.format('Excluir', self.model._meta.verbose_name)
            form = dict(type='form', icon='trash', method='delete', name=name, action=request.path.replace('delete/', ''), fields=serialize_fields(serializer, None, request))
            return Response(form)

    @apidoc(parameters=[])
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
             target = action_class.get_target()
             if target in ('view', 'api', 'user') and action_class.__name__ not in ['Endpoint', 'EndpointSet']:
                k = action_class.get_api_name()
                url_path = k
                if target == 'user':
                    url_path = 'user' if k == 'user' else f'user/{k}'
                methods = action_class.get_api_methods()
                function = create_action_view_func(action_class)
                apidoc(tags=action_class.get_api_tags(), parameters=(['choices_field', 'choices_search'] if 'post' in methods else []), query_fields=action_class.get_query_fields())(function)
                action(detail=False, methods=methods, url_path=url_path, url_name=k, name=k)(function)
                setattr(cls, k, function)
                cls.ACTIONS[k] = action_class


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

        @apidoc(parameters=['q_field', 'only_fields', 'choices_field', 'choices_search', 'page_size', 'relation_page', 'subset_param'], filters=_item.filters)
        def list(self, *args, **kwargs):
            return super().list(*args, **kwargs)

    action_names = []
    action_names.extend(item.actions)
    for fieldset in item.view_fields.values():
        action_names.extend(fieldset.get('actions'))

    for qualified_name in action_names:
        if qualified_name in ('add', 'view', 'edit', 'delete', 'list'): continue
        cls = ACTIONS[qualified_name]
        k = cls.get_api_name()
        url_path = k
        function = create_action_func(cls)
        method = 'post' if cls.get_form_fields() else 'get'
        methods = ['post', 'get'] if specification.app else [method]
        parameters = ['only_fields', 'choices_field', 'choices_search']
        if cls.get_target() == 'instances' or cls.get_target() == 'queryset':
            detail = False
            if cls.get_target() == 'instances':
                url_path = f'{k}/(?P<ids>[0-9,]+)'
                parameters.append('ids_parameter')
        else:
            detail = True
            parameters.append('id_parameter')
        apidoc(parameters=parameters, query_fields=cls.get_query_fields())(function)
        action(detail=detail, methods=['post', 'get'], url_path=url_path, url_name=k, name=k)(function)
        setattr(ViewSet, k, function)
        ViewSet.ACTIONS[k] = cls

    for k in item.relations:
        if item.relations[k].get('related_field'):
            function = create_relation_func(k, item.relations[k])
            apidoc(parameters=['only_fields'])(function)
            action(detail=True, methods=['post', 'get'], url_path='{}/add'.format(k), url_name=k, name=k)(function)
            setattr(ViewSet, k, function)
        for qualified_name in item.relations[k].get('actions'):
            if qualified_name in ('add', 'view', 'edit', 'delete', 'list'): continue
            cls2 = ACTIONS[qualified_name]
            if cls2.get_target() == 'queryset':
                k2 = cls2.get_api_name()
                method = 'post' if cls2.get_form_fields() else 'get'
                methods = ['post', 'get'] if specification.app else [method]
                function = create_action_func(cls2, item.relations[k]['name'])
                apidoc(parameters=['only_fields', 'choices_field', 'choices_search'])(function)
                action(detail=True, methods=['post', 'get'], url_path=k2, url_name=k2, name=k2)(function)
                setattr(ViewSet, k2, function)
                ViewSet.ACTIONS[k2] = cls2
    return ViewSet


def create_action_view_func(action_class):
    def func(self, request, *args, **kwargs):
        serializer = action_class(context=dict(request=request, view=self), instance=request.user)
        if not serializer.check_permission():
            raise exceptions.PermissionDenied(' You do not have permission to perform this action.', 403)
        return serializer.to_response()

    func.__name__ = action_class.get_api_name()
    return func

def create_relation_func(func_name, relation):
    def func(self, request, **kwargs):
        instance = self.model.objects.get(pk=kwargs['pk'])
        serializer = self.get_serializer_class()(
            data=request.data, context=dict(request=request, view=self)
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
            attr = getattr(instance, relation['name'])
            relation_model = attr.model if hasattr(attr, 'model') else attr().model
            relation_item = specification.getitem(relation_model)
            name = '{}_{}'.format('Adicionar', relation_model._meta.verbose_name)
            fieldsets = relation.get('fieldsets', relation_item.add_fieldsets)
            form = dict(type='form', method='post', name=name, action=request.path, fields=serialize_fields(serializer, fieldsets, request))
            return Response(form)

        if serializer.is_valid():
            serializer.validated_data[relation['related_field']] = instance
            try:
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            except ValidationError as e:
                return Response({'non_field_errors': e.message}, status=status.HTTP_400_BAD_REQUEST)
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
        if not serializer.check_permission():
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
        if '.' not in name and relation['actions'] or relation.get('subsets'):
            attr = getattr(model(pk=0), name)
            subitem = specification.getitem(attr.model if hasattr(attr, 'model') else attr().model)
            if subitem:
                for name in relation['actions']:
                    subitem.actions.add(name)
                subsets = relation.get('subsets')
                if subsets:
                    for subset in subsets.values():
                        if subset:
                            for name in subset.get('actions', ()):
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

ActionViewSet.create_actions()

router.register('', ActionViewSet, 'api')


def api_watchdog(sender, **kwargs):
    sender.extra_files.add(Path('api.yml'))

autoreload_started.connect(api_watchdog)

