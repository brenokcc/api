import os
import decimal
from django.conf import settings
import datetime
from inspect import isfunction, ismethod

from django.db import models
from django.db.models.query import ModelIterable
from django.db.models.fields.files import FieldFile
from rest_framework import serializers
from rest_framework.relations import MANY_RELATION_KWARGS
from rest_framework.serializers import RelatedField, ManyRelatedField, ChoiceField, MultipleChoiceField, ModelSerializer

from . import ValueSet
from . import permissions
from .components import Link, Image
from .utils import to_snake_case, to_choices
from .endpoints import ACTIONS, actions_metadata, TextField
from .pagination import PageNumberPagination, PaginableManyRelatedField
from .specification import API
from .exceptions import JsonResponseReadyException


NONE = '__NONE__'

MASKS = dict(
    telefone='(99) 99999-9999',
    cpf='999.999.999-99',
)

def serialize_fields(serializer, fieldsets=None, request=None):
    rel = request.GET.get('rel')
    specification = API.instance()
    allfields = {}
    instance = serializer.instance if isinstance(serializer, ModelSerializer) else None
    for name, field in serializer.fields.items():
        if name in ('id', rel): continue
        extra = {}

        for k, v in MASKS.items():
            if k in name:
                extra.update(mask=v)
                break

        if isinstance(field, MultipleChoiceField):
            field_type = 'select'
            extra.update(multiple=True)
            choices = [dict(id=k, text=v) for k, v in field.choices.items()]
            extra.update(choices=choices)
            value = [choice for choice in choices if choice['id'] in (field.initial or ())]
            if (getattr(field, 'pick', False)):
                extra.update(pick=True)
        elif isinstance(field, ChoiceField):
            field_type = 'select'
            extra.update(multiple=False)
            value = getattr(instance, name) if instance else field.initial
            choices = [dict(id=k, text=v) for k, v in field.choices.items()]
            extra.update(choices=choices)
            if (getattr(field, 'pick', False)):
                extra.update(pick=True)
            else:
                choices.insert(0, dict(id='', text=''))
        elif isinstance(field, ManyRelatedField):
            if getattr(field.child_relation, 'addable', False):
                item = specification.getitem(field.child_relation.queryset.model)
                if permissions.check_roles(item.add_lookups, request.user, False):
                    extra.update(add_url='{}add/'.format(item.url))
            field_type = 'select'
            extra.update(multiple=True)
            qs = getattr(instance, name) if instance else field.child_relation.queryset.filter(pk__in=field.initial)
            value = [dict(id=obj.id, text=str(obj)) for obj in qs.all()] if qs else []
            if getattr(field.child_relation, 'pick', False):
                choices = [dict(id=obj.id, text=str(obj)) for obj in field.child_relation.queryset.all()]
                extra.update(choices=choices, pick=True)
        elif isinstance(field, RelatedField):
            if getattr(field, 'addable', False):
                item = specification.getitem(field.queryset.model)
                if permissions.check_roles(item.add_lookups, request.user, False):
                    extra.update(add_url='{}add/'.format(item.url))
            field_type = 'select'
            extra.update(multiple=False)
            obj = getattr(instance, name) if instance else field.queryset and field.queryset.filter(pk=field.initial).first()
            value = dict(id=obj.id, text=str(obj)) if obj else None
            if getattr(field, 'pick', False):
                choices = [dict(id=obj.id, text=str(obj)) for obj in field.queryset.all()]
                extra.update(choices=choices, pick=True)
        elif isinstance(field, serializers.FileField):
            field_type = 'file'
            value = None
        elif isinstance(field, TextField):
            field_type = 'textarea'
            value = getattr(instance, name) if instance else field.initial
        else:
            field_type = type(field).__name__.lower().replace('field', '')

            value = getattr(instance, name, field.initial) if instance else field.initial
            if isinstance(value, datetime.datetime):
                value = value.strftime('%Y-%m-%d %H:%M')
            elif isinstance(value, datetime.date):
                value = value.strftime('%Y-%m-%d')

            if field_type == 'char':
                field_type = 'text'
            if field_type == 'integer':
                field_type = 'number'
            elif field_type ==  'datetime':
                field_type = 'datetime-local'
            elif field_type == 'decimal':
                field_type = 'text'
                extra.update(mask='decimal')
            elif field.style.get('input_type'):
                field_type = field.style.get('input_type')

            if 'senha' in name or 'password' in name:
                field_type = 'password'
            if name == 'cor':
                field_type = 'color'

        field = dict(name=name, type=field_type, label=field.label, value=value, help_text=field.help_text, read_only=field.read_only, required=field.required and not field.read_only)

        field.update(extra)
        allfields[name] = field

    if fieldsets:
        fields = {}
        for k, v in fieldsets.items():
            k = k if k else ''
            fields[k] = []
            allowed = {name: width for name, width in v['fields'].items()}
            for name in allowed:
                if name in allfields:
                    allfields[name]['width'] = allowed[name]
                    fields[k].append(allfields[name])
            if not fields[k]:
                del fields[k]
    else:
        fields = allfields.values()
    return fields


def serialize_value(value, context, output=None, is_relation=False, relation_name=None):
    specification = API.instance()
    if value is None:
        return None
    elif isinstance(value, str):
        return value
    elif isinstance(value, int):
        return value
    elif isinstance(value, datetime.date):
        return value.strftime('%Y-%m-%dT%H:%M:%S')
    if isinstance(value, decimal.Decimal) or isinstance(value, float):
        return str(value).replace('.', ',')
    elif isinstance(value, dict) or isinstance(value, list):
        if type(value) in (Link, Image):
            request = context['request']
            host_url = "{}://{}".format(
                request.META.get('X-Forwarded-Proto', request.scheme), request.get_host()
            )
            if type(value) == Link and value['url'] and value['url'].startswith('/api/'):
                value['url'] = '{}{}'.format(host_url, value['url'])
            if type(value) == Image and value['src'] and value['src'].startswith('/api/'):
                value['src'] = '{}{}'.format(host_url, value['src'])
        return value
    if isinstance(value, models.QuerySet) and value._iterable_class != ModelIterable:
        return value
    if isinstance(value, models.Manager) or isinstance(value, models.QuerySet) or hasattr(value, 'all'):
        if not isinstance(value, models.QuerySet):
            value = value.all()
        paginator = PageNumberPagination()
        queryset = paginator.paginate_queryset(value, context['request'], context['view'], relation_name)
        fields = output.get('fields') if output else value.metadata.get('fields')
        related_field = output.get('related_field') if output else None
        if related_field and len(fields) == 1:
            meta = dict(model=value.model, exclude=[related_field])
        else:
            meta = dict(model=value.model, fields=fields)
        serializer = DynamicFieldsModelSerializer(
            queryset, many=True, read_only=True, context=context, meta=meta, is_relation=is_relation
        )
        data = serializer.data
        for obj in queryset:
            # TODO checar se está fazendo consulta ou se está usando cache do queryset
            paginator.instances.append(obj)
        return paginator.get_paginated_response(data, metadata=output or value.metadata).data
    elif isinstance(value, models.Model):
        if output:
            meta = dict(model=type(value), fields=output['fields'])
            serializer = DynamicFieldsModelSerializer(
                value, read_only=True, context=context, meta=meta, is_relation=is_relation
            )
            return serializer.data
        else:
            if specification.app:
                return str(value)
            else:
                return dict(id=value.id, text=str(value)) if value else None
    elif isinstance(value, ValueSet):
        value.instance._wrap = True
        data = serialize_value(value.instance, context, dict(fields=value.fields))
        if value.autoreload:
            data['autoreload'] = value.autoreload
        return data
    elif isinstance(value, FieldFile):
        return dict(type='file', url='/api/media{}'.format(value.url), name=value.name.split('/')[-1]) if value else None
    else:
        return value if is_relation else dict(value=value)


class MethodField(serializers.Field):

    def __init__(self, *args, item, method_name=None, **kwargs):
        self.item = item
        self.method_name = method_name
        super().__init__(*args, **kwargs)

    def check_choices_response(self):
        if self.method_name == self.context['request'].GET.get('only'):
            choices = to_choices(getattr(self.parent.instance, self.method_name)(), self.context['request'])
            if choices:
                raise JsonResponseReadyException(choices)

    def to_representation(self, instance):
        value = getattr(instance, self.method_name)()
        relation = self.item.relations.get(self.method_name)
        if relation:
            if not permissions.check_roles(relation.get('requires'), self.context['request'].user, False):
                return NONE
            if isinstance(value, models.QuerySet):
                value = value.contextualize(self.context['request'], relation)
            subset = self.context['request'].GET.get('subset')
            if subset == 'all':
                subset = None
            if subset and 'subsets' in relation:
                subset_metadata = relation['subsets'][subset]
                if subset_metadata:
                    relation = {k:v for k, v in relation.items()}
                    relation['fields'] = subset_metadata.get('fields') or relation['fields']
        data = serialize_value(value, self.context, output=relation, is_relation=True)
        if isinstance(value, models.QuerySet):
            data['relation'] = self.method_name.replace('get_', '')
        return data


class RelationSerializer(serializers.RelatedField):

    def __init__(self, *args, **kwargs):
        self.addable = kwargs.pop('addable', False)
        self.pick = kwargs.pop('pick', False)
        self.specification = API.instance()
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        if self.context['view'].action in ['update']:
            return value.pk if value else None
        relation_name = self.parent.field_name or self.source
        if not isinstance(self.root, serializers.ListSerializer):
            model = type(self.root.instance)
            key = '{}.{}'.format(model._meta.app_label, model._meta.model_name)
            item = self.specification.items.get(key)
            relation = item.relations.get(relation_name)
            if relation:
                if not permissions.check_roles(relation.get('requires'), self.context['request'].user, False):
                    return NONE
                if relation.get('fields'):
                    fields = relation.get('fields')
                    related_field = relation.get('related_field')
                    exclude = (related_field,) if related_field and len(fields)==1 else None
                    meta = dict(model=type(value), fields=fields, exclude=exclude)
                    self.serializer = DynamicFieldsModelSerializer(
                        instance=value, meta=meta,
                        context=self.context, is_relation=True
                    )
                    return self.serializer.data
        if self.specification.app:
            return str(value)
        else:
            return dict(id=value.id, text=str(value)) if value else None

    def to_internal_value(self, data):
        if data is None:
            return None
        elif isinstance(data, list):
            return self.queryset.filter(pk__in=data)
        return self.queryset.get(pk=data)

    def get_choices(self, cutoff=None):
        if self.root.instance:
            obj = getattr(self.root.instance, self.field_name) if self.field_name else None
            return {obj.pk: str(obj)} if obj else {}
        return {}

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return PaginableManyRelatedField(**list_kwargs)


class ActionField(serializers.DictField):

    def __init__(self, field_name, serializer_class, context, *args, **kwargs):
        self.specification = API.instance()
        self.field_name = field_name
        self.serializer_class = serializer_class
        super().__init__(*args, **kwargs)
        self.context.update(context)

    def check_choices_response(self):
        if self.field_name == self.context['request'].GET.get('only'):
            choices = to_choices(self.serializer_class().get(), self.context['request'])
            if choices:
                raise JsonResponseReadyException(choices)

    def to_representation(self, value):
        serializer = self.serializer_class(context=self.context, instance=value)
        result = serializer.get()
        item = self.specification.getitem(type(value))
        relation = item.relations.get(self.field_name)
        if relation:
            if not permissions.check_roles(relation.get('requires'), self.context['request'].user, False):
                return NONE
        if isinstance(result, models.QuerySet):
            result = result.contextualize(self.context['request'], relation)
        data = serialize_value(
            result, context=self.context, is_relation=True, relation_name=self.field_name
        )
        return data

    def to_internal_value(self, data):
        return {}


class FieldsetField(serializers.DictField):

    def __init__(self, *args, fieldset=None, request=None, relation_name=None, **kwargs):
        self.specification = API.instance()
        self.only = []
        self.fieldset = fieldset
        self.relation_name = relation_name
        super().__init__(*args, **kwargs)
        if 'only' in request.GET:
            self.only = [name.strip() for name in request.GET['only'].split(',')]

    def to_representation(self, value):
        if self.relation_name:
            value = getattr(value, self.relation_name)
            if value is None:
                return None
        data = {}
        item = self.specification.getitem(type(value))
        requires = self.fieldset.get('requires')
        if requires and not permissions.check_roles(requires, self.context['request'].user, False):
            return NONE
        for attr_name in self.fieldset['fields']:
            if '.' in attr_name:
                cls = ACTIONS[attr_name]
                api_attr_name = cls.get_api_name()
                serializer = cls(context=self.context, instance=value)
                if serializer.check_permission():
                    attr_value = serializer.get()
                else:
                    continue
            elif attr_name.startswith('get_'):
                api_attr_name = attr_name[4:]
                attr_value = getattr(value, attr_name)()
            else:
                api_attr_name = attr_name
                if 'get_{}'.format(attr_name) in item.view_methods:
                    attr_value = getattr(value, 'get_{}'.format(attr_name))()
                else:
                    attr_value = getattr(value, attr_name)
            if (isinstance(attr_value, models.Manager) or isinstance(attr_value, models.QuerySet) or hasattr(attr_value, 'all')):
                attr_value = [{'id': obj.id, 'text': str(obj)} for obj in attr_value.all()]
            data[api_attr_name] = serialize_value(attr_value, self.context)
        return data

    def to_internal_value(self, data):
        return {attr: data[attr] for attr in self.fieldset['fields']}


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    serializer_related_field = RelationSerializer

    def __init__(self, *args, is_relation=False, **kwargs):
        self.is_relation = is_relation
        meta = kwargs.pop('meta', None)
        if meta:
            metadata = dict(model=meta['model'])
            exclude = meta.get('exclude')
            if exclude:
                metadata['exclude'] = exclude
            else:
                metadata['fields'] = [k for k in meta['fields']] if len(meta['fields']) > 1 else '__all__'
            self.Meta = type("Meta", (), metadata)
        self.item  = API.instance().getitem(self.Meta.model)
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)
        if is_relation:
            for name in list(self.fields):
                if type(self.fields[name]) == PaginableManyRelatedField:
                    self.fields.pop(name)
        else:
            self.remove_unrequested_fields()
        # threadlocals.data.request = self.context.get('request')
        #self.fields['reitor'].style['base_template'] = 'autocomplete.html'
        if self.item.add_hide and self.context['view'] and self.context['view'].action in ('create', 'update'):
            for k, lookups in self.item.add_hide.items():
                pks = permissions.apply_lookups(
                    self.fields[k].queryset, lookups, self.context['request'].user
                ).values_list('pk', flat=True)[0:2]
                if len(pks) == 1:
                    self.fields[k].initial = pks[0]

    def get_real_field_name(self, name):
        for k, field in self.fields.items():
            if isinstance(field, MethodField):
                if k == name:
                    return field.method_name
            elif isinstance(field, ActionField):
                if name == field.serializer_class.get_api_name():
                    return field.field_name
        return name

    def remove_unrequested_fields(self):
        names = self.context['request'].query_params.get('only')
        if names:
            allowed = set()
            for name in names.split(','):
                allowed.add(name.strip())
                allowed.add(self.get_real_field_name(name.strip()))
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def build_property_field(self, field_name, model_field):
        field_cls, field_kwargs = super().build_property_field(field_name, model_field)
        if issubclass(field_cls, serializers.ReadOnlyField) and field_name.startswith('get_'):
            return MethodField, dict(source='*', item=self.item, method_name=field_name)
        return field_cls, field_kwargs

    def build_relational_field(self, field_name, relation_info):
        action = self.context['view'].action
        method_name = 'get_{}'.format(field_name)
        if action in ('list', 'retrieve') and method_name in self.item.view_methods:
            field_cls, field_kwargs = MethodField, dict(source='*', item=self.item, method_name=method_name)
        elif action == 'retrieve' and field_name in self.item.view_fields and not self.is_relation and isinstance(relation_info.model_field, models.ForeignKey):
            fieldset = self.item.view_fields[field_name]
            field_cls, field_kwargs = FieldsetField, dict(
                source='*', fieldset=fieldset, request=self.context['request'], relation_name=field_name,
                help_text='Returns {}'.format(fieldset['fields'])
            )
        elif action == 'list' and field_name in self.item.list_fieldsets:
            fieldset = self.item.list_fieldsets[field_name]
            field_cls, field_kwargs = FieldsetField, dict(
                source='*', fieldset=fieldset, request=self.context['request'], relation_name=field_name,
                help_text='Returns {}'.format(fieldset['fields'])
            )
        else:
            field_cls, field_kwargs = super().build_relational_field(field_name, relation_info)
            if field_cls == RelationSerializer:
                field_kwargs.update(pick=getattr(relation_info.model_field, 'pick', False))
                field_kwargs.update(addable=getattr(relation_info.model_field, 'addable', False))
        return field_cls, field_kwargs

    def build_standard_field(self, field_name, model_field):
        method_name = 'get_{}'.format(field_name)
        if method_name in self.item.view_methods and self.context['view'].action in ('list', 'retrieve'):
            field_cls, field_kwargs = MethodField, dict(source='*', item=self.item, method_name=method_name)
        else:
            field_cls, field_kwargs = super().build_standard_field(field_name, model_field)
            if issubclass(field_cls, serializers.DecimalField):
                field_kwargs.update(localize=True)
        return field_cls, field_kwargs

    def build_unknown_field(self, field_name, model_class):
        action = self.context['view'].action
        method_name = 'get_{}'.format(field_name)
        if action in ('list', 'retrieve') and method_name in self.item.view_methods:
            return MethodField, dict(source='*', item=self.item, method_name=method_name)
        if field_name in ACTIONS:
            return ActionField, dict(
                source='*', field_name=field_name, serializer_class=ACTIONS[field_name], context=self.context
            )
        if field_name in self.item.view_fields:
            fieldset = self.item.view_fields[field_name]
            return FieldsetField, dict(
                source='*', fieldset=fieldset, request=self.context['request'],
                help_text='Returns {}'.format(fieldset['fields'])
            )
        super().build_unknown_field(field_name, model_class)

    def to_representation(self, instance):
        specification = API.instance()
        for field in self._readable_fields:
            if isinstance(field, PaginableManyRelatedField) or isinstance(field, ActionField) or isinstance(field, MethodField):
                field.check_choices_response()
        if self.context['view'].paginator:
            self.context['view'].paginator.instances.append(instance)
        representation = {}
        for k, v in super().to_representation(instance).items():
            if v is not NONE:
                if k.startswith('get_'):
                    k = k[4:]
                elif '.' in k:
                    k = ACTIONS[k].get_api_name()
            representation[k] = v

        if specification.app and getattr(instance, '_wrap', False):
            base_url = '/api/{}/'.format(self.item.prefix)
            result = {}
            for k, v in representation.items():
                if isinstance(v, dict) and v.get('type') is None:
                    metadata = self.item.view_fields.get(self.get_real_field_name(k)) if self.item.view_fields else None
                    result[k] = dict(type="fieldset", fields=[], actions=actions_metadata(
                            instance, metadata.get('actions') if metadata else [], self.context, base_url, [instance]
                    ))
                    for action in result[k]['actions']:
                        action['url'] = action['url'].format(id=instance.id)
                    n = len(v)
                    for x, y in v.items():
                        width = 100
                        if metadata:
                            try:
                                width = metadata['fields'][x]
                            except KeyError:
                                width = metadata['fields'].get(f'get_{x}', 100)
                        result[k]['fields'].append(dict(key=x, value=y, width=width))
                else:
                    result[k] = v
            representation = {
                'type': 'instance', 'id': instance.id, 'str': str(instance), 'icon': self.item.icon, 'result': result,
                'actions': actions_metadata(
                    instance, self.item.view_actions, self.context, base_url, [instance]
                ), 'url': self.context['request'].get_full_path()
            }
            for action in representation['actions']:
                action['url'] = action['url'].format(id=instance.id)
            #for k, v in representation.items(): print(k, v)
        else:
            if set(representation.keys()) == {'', 'id'}:
                representation = representation['']
        return representation
