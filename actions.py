import os
import yaml
import decimal
import json
import re
import datetime
import traceback
from django.apps import apps
from django.db import models
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Role
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from .permissions import check_roles, check_lookups, apply_lookups
from .icons import ICONS
from .components import Boxes
from .utils import to_snake_case, as_choices
from .exceptions import JsonResponseReadyException
from .specification import API
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.cache import cache
from django.conf import settings
from django.db.models import QuerySet


ACTIONS = {}

CharField = serializers.CharField
BooleanField = serializers.BooleanField
IntegerField = serializers.IntegerField
DateField = serializers.DateField
FileField = serializers.FileField
DecimalField = serializers.DecimalField
EmailField = serializers.EmailField
ManyRelatedField = serializers.ManyRelatedField


class TextField(serializers.CharField):
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
        super().__init__(*args, **kwargs)

    def to_internal_value(self, value):
        return self.queryset.get(pk=value) if value else None


def actions_metadata(source, actions, context, base_url, instances=(), viewer=None):
    l = []
    for qualified_name in actions:
        cls = ACTIONS[qualified_name]
        name = cls.get_api_name()
        icon = cls.metadata('icon')
        serializer = cls(context=context, instance=source)
        if issubclass(cls, BatchAction):
            ids = []
            target = 'instances'
            url = f'{base_url}{name}/'
            append = serializer.has_permission()
        elif issubclass(cls, QuerySetAction):
            ids = []
            target = 'queryset'
            url = f'{base_url}{name}/'
            url = '{}{}/'.format(context['request'].path, name)
            append = serializer.has_permission()
        else:
            target = 'instance'
            if name in ('view', 'preview'):
                icon = 'eye'
                url = f'{base_url}{{id}}/' if viewer is None else f'{base_url}{{id}}/{viewer}/'
            else:
                url = f'{base_url}{{id}}/{name}/'
            ids = serializer.check_permission(instances)
            append = True
        if append:
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


class ActionMetaclass(serializers.SerializerMetaclass):
    def __new__(mcs, name, bases, attrs):
        meta = attrs.get('Meta')
        if meta:
            model = getattr(meta, 'model', None)
            fields = getattr(meta, 'fields', None)
            fieldsets = getattr(meta, 'fieldsets', None)
            if model:
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


class Action(serializers.Serializer, metaclass=ActionMetaclass):
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

    @classmethod
    def get_name(cls):
        return cls.metadata('title', to_snake_case(cls.__name__))

    @classmethod
    def get_api_tags(cls):
        return [cls.metadata('api_tag', '')]

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
        return ['get'] if cls.is_action_view() and not cls._declared_fields else ['get', 'post']

    @classmethod
    def is_action_view(cls):
        return cls.view != Action.view

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

    def execute(self, task):
        self.user_task = task.key
        task.start()

    def load(self):
        pass

    def hide(self, *names):
        self.controls['hide'].extend(names)

    def show(self, *names):
        self.controls['show'].extend(names)

    def get(self, name, default=None):
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
        return self.get_internal_value(name, value, default=default)

    def get_internal_value(self, name, value, default=None):
        if value is None:
            return default
        else:
            try:
                value = self.fields[name].to_internal_value(value)
            except ValidationError:
                pass
            return default if value is None else value

    def set(self, **kwargs):
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

    def submit(self):
        if hasattr(self, 'save'):
            if isinstance(self, serializers.ModelSerializer):
                self.instance.save()
        self.notify('Ação realizada com sucesso.')
        return {}

    def has_permission(self):
        return self.user.is_superuser

    def notify(self, message):
        self.user_message = str(message).replace('\n', '<br>')

    def redirect(self, url):
        raise JsonResponseReadyException(dict(redirect=url))

    @property
    def user(self):
        return super().context['request'].user

    @property
    def request(self):
        return super().context['request']

    def check_permission(self, instances=()):
        ids = []
        for instance in instances:
            self.instance = instance
            if self.has_permission():
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

    def requires(self, *role_names, **scopes):
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

    def view(self):
        return None
    
    def get_result(self):
        if self.metadata('cache'):
            ley = '{}.{}'.format(self.context['request'].user.id, type(self).__name__)
            value = cache.get(ley)
            if value is None:
                value = self.view() if self.is_action_view() else self.submit()
                cache.set(ley, value)
        else:
            value = self.view() if self.is_action_view() else self.submit()
        return value

    @classmethod
    def metadata(cls, name, default=None):
        metaclass = getattr(cls, 'Meta', None)
        if metaclass:
            return getattr(metaclass, name, default)
        return default

    def get_url(self):
        return '/api/v1/{}/'.format(
            to_snake_case(type(self).__name__)
        ) if isinstance(self, ActionView) else self.request.path

    def host_url(self):
        return "{}://{}".format(self.request.META.get('X-Forwarded-Proto', self.request.scheme), self.request.get_host())

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
                    values[k] = self.fields[k].to_internal_value(v)
            getattr(self, f'on_{on_change}_change')(**values)
            return Response(self.controls)
        only = self.request.query_params.get('only')
        choices = self.request.query_params.get('choices_field')
        if choices and not only and choices!='seacher':
            self.load()
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

        if self.request.method == 'GET' and not self.is_submitted():
            self.is_valid()
            form = dict(
                type='form', method=self.get_method().lower(), name=self.get_name(), icon=self.metadata('icon'),
                action=self.get_url(), fields=serialize_fields(self, self.fieldsets or self.metadata('fieldsets')),
                controls=self.controls, watch=self.watchable_field_names(), style=self.metadata('style'),
                help_text=self.get_help_text()
            )
            if self.instance and self.metadata('display'):
                self.instance._wrap = True
                try:
                    display = serialize_value(self.instance, self.context, output=dict(fields=self.metadata('display')))
                    display['actions'] = []
                except JsonResponseReadyException as e:
                    return Response(e.data)
                form.update(display=display)
            return Response(form)
        else:
            if not self.fields or self.is_valid():
                try:
                    result = self.get_result()
                except JsonResponseReadyException as e:
                    return Response(e.data)
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


class ActionView(Action):
    pass

class UserAction(Action):
    pass

class BatchAction(Action):
    modal = True

class QuerySetAction(Action):
    modal = True

class ActionSet(ActionView):
    actions = []

    def view(self):
        from .serializers import serialize_value
        result = {}
        path = self.request.path
        only = self.request.GET.get('only')
        for cls in self.actions:
            cls = ACTIONS[cls] if isinstance(cls, str) else cls
            self.request.path = '/api/v1/{}/'.format(cls.get_api_name())
            action = cls(context=self.context, instance=self.request.user)
            if action.has_permission() and (only is None or cls.get_api_name()==only):
                if action.metadata('sync', True) or action.is_cached() or cls.get_api_name()==only:
                    response = action.to_response()
                    if response.data is not None:
                        result[cls.get_api_name()] = response.data
                else:
                    result[cls.get_api_name()] = dict(type='async', url='{}?only={}'.format(path, cls.get_api_name()))
        self.request.path = path
        return result


class Shortcuts(ActionView):

    class Meta:
        api_tag = 'api'

    def view(self):
        boxes = Boxes('Acesso Rápido')
        specification = API.instance()
        for k, item in specification.items.items():
            if item.icon and check_roles(item.list_lookups, self.user, False):
                label = apps.get_model(k)._meta.verbose_name_plural
                boxes.append(item.icon, label, item.url)
        return boxes if boxes else None

    def has_permission(self):
        return self.instance.is_authenticated

class Dashboard(ActionSet):
    actions = Shortcuts,

    class Meta:
        api_tag = 'api'

    def has_permission(self):
        return self.user.is_authenticated


class Icons(ActionView):
    class Meta:
        api_tag = 'api'

    def view(self):
        return dict(type='icons', icons=ICONS)

    def has_permission(self):
        return True

class Application(ActionView):

    class Meta:
        api_tag = 'api'

    def view(self):
        with open(os.path.join(settings.BASE_DIR, 'i18n.yml')) as file:
            i18n = yaml.safe_load(file)
        specification = API.instance()
        index_url = '/api/v1/index/' if specification.index else '/api/v1/login/'
        nocolor = 'radius',
        theme = {k: v if k in nocolor else '#{}'.format(v).strip() for k, v in specification.theme.items()}
        oauth = []
        for name, provider in specification.oauth.items():
            redirect_uri = "{}{}".format(self.request.META.get('HTTP_ORIGIN', self.host_url()), provider['redirect_uri'])
            authorize_url = '{}?response_type=code&client_id={}&redirect_uri={}'.format(
                provider['authorize_url'], provider['client_id'], redirect_uri
            )
            if provider.get('scope'):
                authorize_url = '{}&scope={}'.format(authorize_url, provider.get('scope'))
            oauth.append(dict(label=f'Entrar com {provider["name"]}', url=authorize_url))
        data = dict(
            title=specification.title,
            subtitle=specification.subtitle,
            footer=specification.footer,
            icon=specification.icon,
            logo=specification.logo,
            theme=theme,
            i18n=i18n,
            menu=[],
            oauth=oauth,
            index=index_url
        )
        url = self.host_url()
        if data['icon'] and data['icon'].startswith('/'):
            data['icon'] = '{}{}'.format(url, data['icon'])
        if data['logo'] and data['logo'].startswith('/'):
            data['logo'] = '{}{}'.format(url, data['logo'])
        if data['footer'] and data['footer'].get('logo') and data['footer']['logo'].startswith('/'):
            data['footer']['logo'] = '{}{}'.format(url, data['footer']['logo'])
        return data

    def has_permission(self):
        return True


class UserRoles(Action):

    @classmethod
    def get_api_name(cls):
        return 'user_roles'

    def view(self):
        return [str(role) for role in Role.objects.filter(username=self.instance.username).order_by('id')]


class ActivateRole(Action):

    def submit(self):
        qs = self.objects('api.role').filter(username=self.instance.username)
        qs.update(active=False)
        qs.filter(id=self.instance.id).update(active=True)
        self.notify('Papel ativado com sucesso')
        self.redirect('/api/v1/dashboard/')

    def has_permission(self):
        return self.user.is_superuser or self.user.username == self.instance.username


class UserResources(UserAction):

    @classmethod
    def get_api_name(cls):
        return 'resources'

    def view(self):
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

    def has_permission(self):
        return self.user.is_authenticated


class ChangePassword(UserAction):

    senha = serializers.CharField(label='Senha')

    class Meta:
        icon = 'user-shield'
        display = 'last_login',

    def submit(self):
        self.instance.set_password(self.get('senha'))
        self.instance.save()
        if self.instance == self.request.user:
            token = Token.objects.get_or_create(user=self.user)[0]
            user = dict(id=self.user.id, username=self.user.username, is_superuser=self.user.is_superuser)
            return {'token': token.key, 'user': user}
        else:
            self.notify('Senha alterada com sucesso')

    def has_permission(self):
        return self.user.is_superuser or self.user == self.instance


class ChangePasswords(BatchAction):

    senha = serializers.CharField(label='Senha')

    class Meta:
        icon = 'user-shield'

    def submit(self):
        for user in self.instance.all():
            user.set_password(self.data['senha'])
            user.save()


class VerifyPassword(UserAction):
    senha = serializers.CharField(label='Senha')

    def submit(self):
        return self.notify(self.instance.check_password(self.data['senha']))

    def has_permission(self):
        return True


class TaskProgress(ActionView):
    class Meta:
        api_tag = 'api'

    def view(self):
        value = cache.get(self.request.GET.get('key'), 0)
        return value
