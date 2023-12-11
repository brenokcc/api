import os
import io
import yaml
import decimal
import json
import re
import requests
import datetime
import traceback
import subprocess
from uuid import uuid1
from api.utils import related_model
from django.apps import apps
from django.db import models
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Role, Email
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from .permissions import check_roles, check_lookups, apply_lookups
from .icons import ICONS
from .components import Boxes
from .utils import to_snake_case, as_choices, to_csv_temp_file, to_xls_temp_file
from .exceptions import JsonResponseReadyException
from .specification import API, str_to_width_list
from .tasks import TaskRunner
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.cache import cache
from django.conf import settings
from django.contrib import auth
from django.http import HttpResponse, FileResponse
from django.db.models import QuerySet
from . import permissions


ACTIONS = {}
TARGET_USER = 'user'
TARGET_INSTANCE = 'instance'
TARGET_INSTANCES = 'instances'
TARGET_QUERYSET = 'queryset'

CharField = serializers.CharField
BooleanField = serializers.BooleanField
IntegerField = serializers.IntegerField
DateField = serializers.DateField
FileField = serializers.FileField
DecimalField = serializers.DecimalField
EmailField = serializers.EmailField
ManyRelatedField = serializers.ManyRelatedField
HiddenField = serializers.HiddenField


class TextField(serializers.CharField):
    pass


class QueryField(HiddenField):
    pass


serializers.ModelSerializer.serializer_field_mapping[models.TextField] = TextField


class ChoiceField(serializers.ChoiceField):

    def __init__(self, *args, **kwargs):
        self.pick = kwargs.pop('pick', False)
        super().__init__(*args, **kwargs)


class MultipleChoiceField(serializers.MultipleChoiceField):

    def __init__(self, *args, **kwargs):
        self.pick = kwargs.pop('pick', False)
        super().__init__(*args, **kwargs)


class RelatedField(serializers.RelatedField):

    def __init__(self, *args, **kwargs):
        self.pick = kwargs.pop('pick', False)
        self.addable = kwargs.pop('addable', False)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, value):
        return self.queryset.get(pk=value) if value else None


def actions_metadata(source, actions, context, base_url, instances=(), viewer=None, related_field=None):
    l = []
    for qualified_name in actions:
        cls = ACTIONS[qualified_name]
        name = cls.get_api_name()
        icon = cls.metadata('icon')
        serializer = cls(context=context, instance=source)
        if cls.get_target() == 'instances':
            ids = []
            target = 'instances'
            url = f'{base_url}{name}/'
            append = serializer.check_permission()
        elif cls.get_target() == 'queryset':
            ids = []
            target = 'queryset'
            url = f'{base_url}{name}/'
            url = '{}{}/'.format(context['request'].path, name)
            append = serializer.check_permission()
        else:
            target = 'instance'
            if name in ('view', 'preview'):
                icon = 'eye'
                url = f'{base_url}{{id}}/' if viewer is None else f'{base_url}{{id}}/{viewer}/'
            else:
                url = f'{base_url}{{id}}/{name}/'
            ids = serializer.test_permission(instances)
            append = bool(ids)
        if append:
            if qualified_name == 'edit' and related_field:
                url = '{}?rel={}'.format(url, related_field)
            l.append(dict(name=cls.metadata('title', name), url=url, icon=icon, target=target, modal=cls.metadata('modal', True), style=cls.metadata('style', 'primary'), ids=ids))
    return l


class UserCache(object):

    def __init__(self, user):
        self.user = user

    def set(self, k, v):
        cache.set(self.key(k), v, timeout=None)

    def get(self, k, default=None):
        return cache.get(self.key(k), default)

    def key(self, k):
        return '{}-{}'.format(self.user.username, k)

    def delete(self, k):
        return cache.delete(self.key(k))


class EnpointMetaclass(serializers.SerializerMetaclass):
    def __new__(mcs, name, bases, attrs):
        meta = attrs.get('Meta')
        if meta:
            model = getattr(meta, 'model', None)
            fields = getattr(meta, 'fields', None)
            fieldsets = getattr(meta, 'fieldsets', None)
            if model:
                if isinstance(model, str):
                    setattr(meta, 'model', apps.get_model(model))
                bases = bases + (serializers.ModelSerializer,)
            if fields is None and fieldsets:
                fields = []
                for names in fieldsets.values():
                    for str_or_tuple in names:
                     fields.append(str_or_tuple) if isinstance(str_or_tuple, str) else fields.extend(str_or_tuple)
                setattr(meta, 'fields', fields)
        cls = super().__new__(mcs, name, bases, attrs)
        ACTIONS[cls.get_qualified_name()] = cls
        return cls


class Endpoint(serializers.Serializer, metaclass=EnpointMetaclass):
    permission_classes = AllowAny,

    class Meta:
        icon = None
        cache = None
        modal = True
        sync = True
        fieldsets = {}

    def __init__(self, *args, **kwargs):
        self.user_task = None
        self.user_message = None
        self.user_redirect = None
        self.instance = kwargs.get('instance')
        self.cache = None
        self.fieldsets = {}
        self.controls = dict(hide=[], show=[], set={})

        data = None
        if 'context' in kwargs:
            request = kwargs['context']['request']
            self.cache = UserCache(request.user)
            if request.method.upper() == 'POST':
                data = request.POST or request.data
            else:
                data = request.GET or request.data or None

        super().__init__(data=data, *args, **kwargs)
        for name in [k for k, v in self.fields.items() if type(v) == QueryField]:
            del self.fields[name]

    @property
    def instances(self):
        return self.instance

    @classmethod
    def get_icon(cls):
        return cls.metadata('icon', None)

    @classmethod
    def get_target(cls):
        return cls.metadata('target', 'view')

    @classmethod
    def get_name(cls):
        return cls.metadata('title', to_snake_case(cls.__name__))

    @classmethod
    def get_api_tags(cls):
        target = cls.get_target()
        if target == 'user':
            api_tag = 'user'
        elif target == 'api':
            api_tag = 'api'
        else:
            api_tag = ''
        return [api_tag]

    @classmethod
    def get_api_name(cls):
        return to_snake_case(cls.__name__)

    @classmethod
    def get_qualified_name(cls):
        return '{}.{}'.format(cls.__module__, cls.__name__).lower()

    @classmethod
    def get_method(cls):
        return 'GET' if cls.is_action_view() else 'POST'

    @classmethod
    def get_api_methods(cls):
        return ['get'] if cls.is_action_view() and not cls.get_form_fields() else ['get', 'post']

    @classmethod
    def is_action_view(cls):
        return cls.get != Endpoint.get

    @classmethod
    def get_query_fields(cls):
        return {name: field for name, field in cls._declared_fields.items() if isinstance(field, QueryField)}

    @classmethod
    def get_form_fields(cls):
        return {name: field for name, field in cls._declared_fields.items() if not isinstance(field, QueryField)}

    def get_help_text(self):
        return self.metadata('help_text')

    def is_submitted(self):
        if self.fields:
            if self.request.GET.get('submit') == self.get_name():
                return True
            for k in self.fields:
                if k in self.request.GET or k in self.request.POST or k in self.request.GET:
                    return True
            return False
        return self.is_action_view() or self.request.method != 'GET'

    def execute(self, task, message=None):
        self.user_task = task.key
        self.user_message = message if message else self.user_message
        TaskRunner(task).start()

    def load(self):
        pass

    def disable(self, *names):
        self.controls['hide'].extend(names)

    def enable(self, *names):
        self.controls['show'].extend(names)

    def getdata(self, name, default=None):
        value = None
        if name in self.fields and (isinstance(self.fields[name], MultipleChoiceField) or (isinstance(self.fields[name], ManyRelatedField))):
            if name in self.request.GET:
                value = self.request.GET.getlist(name)
            elif name in self.request.POST:
                value = self.request.POST.getlist(name)
        else:
            if name in self.request.GET:
                value = self.request.GET[name]
            elif name in self.request.POST:
                value = self.request.POST[name]
            elif name in self.request.data:
                value = self.request.data[name]
        return self.get_internal_value(name, value, default=default)

    def get_internal_value(self, name, value, default=None):
        if value is None:
            return default
        else:
            try:
                value = self.fields[name].to_internal_value(value)
            except KeyError:
                pass
            except ValidationError:
                pass
            return default if value is None else value

    def setdata(self, **kwargs):
        for k, v in kwargs.items():
            if isinstance(v, models.Model):
                v = dict(id=v.id, text=str(v))
            if isinstance(v, bool):
                v = str(v).lower()
            elif isinstance(v, datetime.datetime):
                v = v.strftime('%Y-%m-%d %H:%M')
            elif isinstance(v, datetime.date):
                v = v.strftime('%Y-%m-%d')
            self.controls['set'][k] = v

    def watchable_field_names(self):
        l = []
        for name in self.fields:
            attr_name = f'on_{name}_change'
            if hasattr(self, attr_name):
                l.append(name)
        return l

    def is_valid(self, *args, **kwargs):
        self.load()
        is_valid = super().is_valid(*args, **kwargs)
        if is_valid and isinstance(self, serializers.ModelSerializer):
            for k, v in self.validated_data.items():
                setattr(self.instance, k, v)
        return is_valid

    def post(self):
        if hasattr(self, 'save'):
            for k, field in self.fields.items():
                if isinstance(field, serializers.FileField) and k in self.request.FILES:
                    if hasattr(self.instance, k):
                        file = self.request.FILES[k]
                        filename = '{}.{}'.format(uuid1().hex, file.name.split('.')[-1])
                        getattr(self.instance, k).save(filename, file)
            self.instance.save()
        self.notify()
        return {}

    def check_permission(self):
        return self.user.is_superuser

    def notify(self, message='Ação realizada com sucesso'):
        self.user_message = str(message).replace('\n', '<br>')

    def redirect(self, url):
        if url.startswith('/'):
            url = '{}{}'.format(self.host_url(), url)
        raise JsonResponseReadyException(dict(redirect=url, message=self.user_message))

    @property
    def user(self):
        return super().context['request'].user

    @property
    def request(self):
        return super().context['request']

    def test_permission(self, instances=()):
        ids = []
        for instance in instances:
            self.instance = instance
            if self.check_permission():
                ids.append(instance.id)
        return ids

    def objects(self, model):
        return apps.get_model(model).objects

    def join(self, *querysets):
        qs = querysets[0]
        for queryset in querysets[1:]:
            qs = qs | queryset
        return qs

    def apply_lookups(self, queryset, *role_names, **scopes):
        lookups = {}
        for name in role_names:
            lookups[name] = scopes
        return apply_lookups(queryset, lookups, self.user)

    def check_roles(self, *role_names, **scopes):
        if self.user.is_superuser:
            return True
        if scopes:
            for name in role_names:
                if check_lookups(self.instance, {name: scopes}, self.user, False):
                    return True
        else:
            for name in role_names:
                if check_roles({name: None}, self.user, False):
                    return True
        return False

    def is_cached(self):
        key = '{}.{}'.format(self.context['request'].user.id, type(self).__name__)
        return cache.has_key(key)

    def get(self):
        return None

    def get_result(self):
        if self.metadata('cache'):
            ley = '{}.{}'.format(self.context['request'].user.id, type(self).__name__)
            value = cache.get(ley)
            if value is None:
                value = self.get() if self.is_action_view() else self.post()
                cache.set(ley, value)
        else:
            value = self.get() if self.is_action_view() else self.post()
        return value

    @classmethod
    def metadata(cls, name, default=None):
        metaclass = getattr(cls, 'Meta', None)
        if metaclass:
            return getattr(metaclass, name, default)
        return default

    def get_url(self):
        url = '/api/{}/'.format(
            to_snake_case(type(self).__name__)
        ) if self.get_target() is None else self.request.path
        querystring = self.request.GET.urlencode()
        if querystring:
            url = '{}?{}'.format(url, querystring)
        return url

    def host_url(self):
        return "{}://{}".format(self.request.META.get('X-Forwarded-Proto', self.request.scheme), self.request.get_host())

    def to_xls_file(self, **sheets):
        return open(to_xls_temp_file(sheets), 'rb')

    def to_csv_file(self, rows):
        return open(to_csv_temp_file(rows), 'rb')

    def get_fieldsets(self):
        fieldsets = {}
        for k, v in (self.fieldsets or self.metadata('fieldsets', {})).items():
            if isinstance(v, str):
                fieldsets[k] = dict(name=k, fields={name: width for name, width in str_to_width_list(v)})
            else:
                fields = {}
                for name in v:
                    if isinstance(name, str):
                        fields[name] = 100
                    else:
                        for name2 in name:
                            fields[name2] = int(100/len(name))
                fieldsets[k] = dict(name=k, fields=fields)
        return fieldsets

    def send_mail(self, to, subject, content, from_email=None):
        Email.objects.send(to, subject, content, from_email)

    def to_response(self, key=None):
        from .serializers import serialize_value, serialize_fields
        on_change = self.request.query_params.get('on_change')
        if on_change:
            self.load()
            self.controls['show'].clear()
            self.controls['hide'].clear()
            self.controls['set'].clear()
            values = {}
            for k, v in self.request.POST.items():
                if k in self.fields and v!='':
                    values[k] = self.get_internal_value(k, v)
            getattr(self, f'on_{on_change}_change')(**values)
            return Response(self.controls)
        only = self.request.query_params.get('only')
        choices = self.request.query_params.get('choices_field')
        self.load()
        if choices and not only and choices in self.fields:
            term = self.request.query_params.get('choices_search')
            field = self.fields[choices]
            if isinstance(field, serializers.ManyRelatedField):
                qs = field.child_relation.queryset.all()
            else:
                qs = field.queryset.all()
            attr_name = f'get_{choices}_queryset'
            if hasattr(self, attr_name):
                qs = getattr(self, attr_name)(qs)
            return Response(as_choices(qs.apply_search(term)))
        if choices and not only and choices not in self.fields:
            term = self.request.query_params.get('choices_search')
            qs = self.get()
            relmodel = related_model(qs.model, choices)
            qs = relmodel.objects.filter(id__in=qs.values_list(choices, flat=True))
            return Response(as_choices(qs.apply_search(term)))

        if self.request.method == 'GET' and not self.is_submitted():
            self.is_valid()
            form = dict(
                type='form', method=self.get_method().lower(), name=self.get_name(), icon=self.metadata('icon'),
                action=self.get_url(), fields=serialize_fields(self, self.get_fieldsets(), self.request),
                controls=self.controls, watch=self.watchable_field_names(), style=self.metadata('style'),
                help_text=self.get_help_text()
            )
            if self.instance and self.metadata('display'):
                self.instance._wrap = True
                try:
                    fields = {k: 100 for k in self.metadata('display')}
                    display = serialize_value(self.instance, self.context, output=dict(fields=fields))
                    display['actions'] = []
                except JsonResponseReadyException as e:
                    return Response(e.data)
                form.update(display=display)
            return Response(form)
        else:
            if not self.fields or self.is_valid():
                try:
                    result = self.get_result()
                    if isinstance(result, HttpResponse):
                        return result
                    if isinstance(result, io.BufferedReader):
                        return FileResponse(result)
                except JsonResponseReadyException as e:
                    return Response(e.data)
                except ValidationError as e:
                    return Response({'non_field_errors': e.detail[0]}, status=status.HTTP_400_BAD_REQUEST)
                except DjangoValidationError as e:
                    return Response({'non_field_errors': e.message}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    traceback.print_exc()
                    return Response({'non_field_errors': 'Ocorreu um erro no servidor ({}).'.format(e)}, status=status.HTTP_400_BAD_REQUEST)
                if result is None:
                    value = None
                elif type(result) in [str, int, float, decimal.Decimal, datetime.date, datetime.datetime]:
                    value = result
                else:
                    metadata = None
                    if isinstance(result, QuerySet):
                        metadata = result.metadata
                        result = result.contextualize(self.request)
                    value = serialize_value(result, self.context, metadata)
                    if key:
                        if isinstance(value, dict) and value.get('type'):
                            pass
                        else:
                            value = {'type': key, 'result': value} if value is not None else None
                response = Response({} if value is None else value, status=status.HTTP_200_OK)
                if self.user_message:
                    response['USER_MESSAGE'] = self.user_message
                    response.data.update(message=self.user_message)
                if self.user_redirect:
                    response['USER_REDIRECT'] = self.user_redirect
                    response.data.update(redirect=self.user_redirect)
                if self.user_task:
                    response['USER_TASK'] = self.user_task
                    response.data.update(task=self.user_task)
                return response
            else:
                return Response(self.errors, status=status.HTTP_400_BAD_REQUEST)


class EndpointSet(Endpoint):
    endpoints = []

    def get(self):
        from .serializers import serialize_value
        result = {}
        path = self.request.path
        only = self.request.GET.get('only')
        for cls in self.endpoints:
            cls = ACTIONS[cls] if isinstance(cls, str) else cls
            self.request.path = '/api/{}/'.format(cls.get_api_name())
            action = cls(context=self.context, instance=self.request.user)
            if action.check_permission() and (only is None or cls.get_api_name()==only):
                if action.metadata('sync', True) or action.is_cached() or cls.get_api_name()==only:
                    response = action.to_response()
                    if response.data is not None:
                        result[cls.get_api_name()] = response.data
                else:
                    result[cls.get_api_name()] = dict(type='async', url='{}?only={}'.format(path, cls.get_api_name()))
        self.request.path = path
        return result


class Shortcuts(Endpoint):

    class Meta:
        target = 'api'

    def get(self):
        boxes = Boxes('Acesso Rápido')
        specification = API.instance()
        for k, item in specification.items.items():
            if item.icon and check_roles(item.list_lookups, self.user, False):
                label = apps.get_model(k)._meta.verbose_name_plural
                boxes.append(item.icon, label, item.url)
        return boxes if boxes['items'] else None

    def check_permission(self):
        return self.instance.is_authenticated

class Dashboard(EndpointSet):
    endpoints = Shortcuts,

    class Meta:
        title = 'Início'
        target = 'api'

    def check_permission(self):
        return self.user.is_authenticated


class Icons(Endpoint):
    class Meta:
        title = 'Ícones'
        target = 'api'

    def get(self):
        return dict(type='icons', icons=ICONS)

    def check_permission(self):
        return self.user.is_superuser


class Oauth(Endpoint):
    code = QueryField(label='Authorization Code', default=None)

    class Meta:
        target = 'api'

    def get(self):
        error = {}
        code = self.getdata('code')
        specification = API.instance()
        for name, provider in specification.oauth.items():
            redirect_uri = "{}{}".format(self.host_url(), provider['redirect_uri'])
            access_token_request_data = dict(
                grant_type='authorization_code', code=code, redirect_uri=redirect_uri,
                client_id=provider['client_id'], client_secret=provider['client_secret']
            )
            response = requests.post(provider['access_token_url'], data=access_token_request_data, verify=False)
            if response.status_code != 200:
                error[name] = response.text
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
                user = self.objects('auth.user').filter(username=username).first()
                if user is None and provider.get('user_data').get('create'):
                    user = self.objects('auth.user').create(
                        username=username,
                        email=data[provider['user_data']['email']] if provider['user_data']['email'] else ''
                    )
                if user:
                    token = Token.objects.get_or_create(user=user)[0]
                    return dict(
                        token=token.key, user=dict(id=user.id, username=user.username, is_superuser=user.is_superuser),
                        redirect='/api/dashboard/', message='Autenticação realizada com sucesso.'
                    )
                else:
                    return dict(type='info', text='Usuário "{}" inexistente.'.format(username))
            else:
                error[name] = response.text
        return dict(type='info', text='Ocorreu um erro ao realizar login: {}'.format(json.dumps(error)))

    def check_permission(self):
        return True


class Login(Endpoint):
    username = CharField(label='Nome do usuário')
    password = CharField(label='Senha')

    class Meta:
        target = 'api'

    def post(self):
        username = self.getdata('username')
        password = self.getdata('password')
        user = self.objects('auth.user').filter(username=username).first()
        if not auth.authenticate(username=username, password=password):
            raise ValidationError('Usuário não autenticado.')
        token = Token.objects.get_or_create(user=user)[0]
        return dict(
            token=token.key, user=dict(id=user.id, username=user.username, is_superuser=user.is_superuser),
            redirect='/api/dashboard/', message='Autenticação realizada com sucesso.'
        )


    def check_permission(self):
        return True


class Logout(Endpoint):

    class Meta:
        target = 'api'

    def get(self):
        self.redirect('/')

    def check_permission(self):
        return True


class Manifest(Endpoint):

    class Meta:
        target = 'api'

    def get(self):
        specification = API.instance()
        return Response(
            {
                "name": specification.title,
                "short_name": specification.title,
                "lang": 'pt-BR',
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "icons": [{
                    "src": '{}{}'.format(self.host_url(), specification.icon),
                    "sizes": "192x192",
                    "type": "image/png"
                }]
            }
        )

    def check_permission(self):
        return True

class Application(Endpoint):

    class Meta:
        target = 'api'

    def __init__(self, *args, **kwargs):
        self.specification = API.instance()
        super().__init__(*args, **kwargs)

    def process_menu_entry(self, menu, entry, i=0):
        endpoint = entry.get('endpoint')
        if endpoint:
            if endpoint.count('.') == 1:
                item = self.specification.items[endpoint]
                if permissions.check_roles(item.list_lookups, self.request.user, raise_exception=False):
                    cls = apps.get_model(endpoint)
                    label = cls._meta.verbose_name_plural.title()
                    icon = (item.icon or 'dot-circle') if i == 0 else None
                    subitem = dict(icon=icon, label=label, url=item.url)
                    menu.append(subitem)
            else:
                cls = ACTIONS[endpoint]
                serializer = cls(context=dict(request=self.request), instance=self.request.user)
                if serializer.check_permission():
                    label = cls.get_name().title().strip()
                    icon = (cls.get_icon() or 'dot-circle') if i == 0 else None
                    subitem = dict(icon=icon, label=label, url='/api/{}/'.format(cls.get_api_name()))
                    menu.append(subitem)
        else:
            label=entry['label']
            icon = None
            if label.endswith(']'):
                tokens = label.split('[')
                label = tokens[0].strip()
                icon = tokens[1].strip(']')
            icon = (icon or 'dot-circle') if i == 0 else None
            subitem = dict(icon=icon, label=label, children=[])
            for child in entry.get('children'):
                self.process_menu_entry(subitem['children'], child, i + 1)
            if subitem['children']:
                menu.append(subitem)

    def get(self):
        with open(os.path.join(settings.BASE_DIR, 'i18n.yml')) as file:
            i18n = yaml.safe_load(file)

        index_url = '/app/index/' if self.specification.index else '/app/login/'
        nocolor = 'radius',
        theme = {k: v if k in nocolor else '#{}'.format(v).strip() for k, v in self.specification.theme.items()}
        oauth = []
        for name, provider in self.specification.oauth.items():
            redirect_uri = "{}{}".format(self.request.META.get('HTTP_ORIGIN', self.host_url()), provider['redirect_uri'])
            authorize_url = '{}?response_type=code&client_id={}&redirect_uri={}'.format(
                provider['authorize_url'], provider['client_id'], redirect_uri
            )
            if provider.get('scope'):
                authorize_url = '{}&scope={}'.format(authorize_url, provider.get('scope'))
            oauth.append(dict(label=f'Entrar com {provider["name"]}', url=authorize_url))

        menu = []
        for entry in self.specification.menu:
            self.process_menu_entry(menu, entry)
        # import json
        # print(json.dumps(app_menu, indent=2, ensure_ascii=False))

        data = dict(
            title=self.specification.title,
            subtitle=self.specification.subtitle,
            footer=self.specification.footer,
            icon=self.specification.icon,
            logo=self.specification.logo,
            theme=theme,
            i18n=i18n,
            menu=menu,
            oauth=oauth,
            index=index_url,
            web_push_notification=self.specification.web_push_notification
        )
        url = self.host_url()
        if data['icon'] and data['icon'].startswith('/'):
            data['icon'] = '{}{}'.format(url, data['icon'])
        if data['logo'] and data['logo'].startswith('/'):
            data['logo'] = '{}{}'.format(url, data['logo'])
        if data['footer'] and data['footer'].get('logo') and data['footer']['logo'].startswith('/'):
            data['footer']['logo'] = '{}{}'.format(url, data['footer']['logo'])
        return data

    def check_permission(self):
        return True


class PushSubscription(Endpoint):

    class Meta:
        title = 'Subscrever para Notificações'

    def post(self):
        data = json.loads(self.getdata('subscription'))
        device = self.request.META.get('HTTP_USER_AGENT', '')
        qs = self.objects('api.pushsubscription').filter(user=self.user, device=device)
        qs.update(data=data) if qs.exists() else self.objects('api.pushsubscription').create(
            user=self.user, data=data, device=device
        )
        self.notify()

    def has_permission(self):
        return True


class PushNotification(Endpoint):
    text = TextField(label='Texto')

    class Meta:
        icon = 'bell'
        target = 'instance'
        title = 'Enviar Notificação'

    def post(self):
        if self.instance.notify(self.getdata('text')):
            self.notify('Notificação enviada com sucesso.')

    def has_permission(self):
        return self.user.is_superuser


class HealthCheck(Endpoint):

    class Meta:
        target = 'api'

    def get(self):
        return dict(status='UP', time=datetime.datetime.now().isoformat())

    def check_permission(self):
        return True


class User(Endpoint):
    class Meta:
        target = 'user'

    def get(self):
        return dict(
            id=self.instance.id,
            username=self.instance.username,
            roles=[
                dict(id=role.id, name=role.get_description(), active=role.active)
                for role in Role.objects.filter(username=self.instance.username)
            ]
        )

    def check_permission(self):
        return self.user.is_authenticated


class UserRoles(Endpoint):

    class Meta:
        target = 'user'

    @classmethod
    def get_api_name(cls):
        return 'user_roles'

    def get(self):
        return [str(role) for role in Role.objects.filter(username=self.instance.username).order_by('id')]


class ActivateRole(Endpoint):

    class Meta:
        target = 'instance'

    def post(self):
        qs = self.objects('api.role').filter(username=self.instance.username)
        qs.update(active=False)
        qs.filter(id=self.instance.id).update(active=True)
        self.notify('Papel ativado com sucesso')
        self.redirect('/api/dashboard/')

    def check_permission(self):
        return self.user.is_superuser or self.user.username == self.instance.username


class UserResources(Endpoint):

    class Meta:
        target = 'user'

    @classmethod
    def get_api_name(cls):
        return 'resources'

    def get(self):
        from .viewsets import specification
        q = self.request.GET.get('choices_search')
        resources = []
        for k, item in specification.items.items():
            name = apps.get_model(k)._meta.verbose_name_plural
            if name.islower():
                name = name.title()
            if q is None or q.lower() in name.lower():
                if check_roles(item.list_lookups, self.user, False):
                    resources.append({'name': name, 'url': item.url})
        return resources

    def check_permission(self):
        return self.user.is_authenticated


class ChangePassword(Endpoint):

    senha = serializers.CharField(label='Senha')

    class Meta:
        icon = 'user-shield'
        target = 'user'

    def post(self):
        self.instance.set_password(self.getdata('senha'))
        self.instance.save()
        if self.instance == self.request.user:
            token = Token.objects.get_or_create(user=self.user)[0]
            user = dict(id=self.user.id, username=self.user.username, is_superuser=self.user.is_superuser)
            return {'token': token.key, 'user': user}
        else:
            self.notify('Senha alterada com sucesso')

    def check_permission(self):
        return self.user.is_superuser or self.user == self.instance


class ChangePasswords(Endpoint):

    senha = serializers.CharField(label='Senha')

    class Meta:
        icon = 'user-shield'
        target = 'instances'

    def post(self):
        for user in self.instance.all():
            user.set_password(self.getdata('senha'))
            user.save()


class VerifyPassword(Endpoint):
    senha = serializers.CharField(label='Senha')

    class Meta:
        icon = 'check'
        target = 'user'

    def post(self):
        checked = self.instance.check_password(self.getdata('senha'))
        if not checked:
            raise ValidationError('Senha não confere.')
        return self.notify('Senha verificada com sucesso.')

    def check_permission(self):
        return self.user.is_superuser


class TaskProgress(Endpoint):
    class Meta:
        target = 'api'

    def get(self):
        data = cache.get(self.request.GET.get('key'), None)
        if data['file_path']:
            return open(data['file_path'], 'rb')
        return data

    def check_permission(self):
        return True


class Shell(Endpoint):
    script = TextField(label='')

    class Meta:
        icon = 'cast'
        title = 'Shell'
        modal = False

    def post(self):
        script = self.getdata('script')
        p = subprocess.Popen(
            ['python', 'manage.py', 'shell', '-c', script],
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        output = '{}{}'.format(stdout.decode(), stderr.decode())
        return dict(type='shell', output=output)

    def has_permission(self):
        return self.user.is_superuser
