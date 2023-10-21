
from decimal import Decimal
from django.db import models
from rest_framework import pagination
from rest_framework import relations
from . import permissions
from .specification import API
from .actions import actions_metadata
from .utils import to_snake_case, to_choices, to_calendar
from .exceptions import JsonResponseReadyException


specification = API.instance()


def filter_field(model, lookups, request):
    name = lookups.strip()
    suffix = None
    choices = None
    field = None
    value = None
    ignore = 'icontains', 'contains', 'gt', 'gte', 'lt', 'lte', 'id', 'year', 'month'
    tmp = []
    for lookup in name.split('__'):
        if lookup in ignore:
            suffix = lookup
        else:
            tmp.append(lookup)
    field = model.get_field('__'.join(tmp)) if tmp else None
    if field:
        if getattr(field, 'choices'):
            field_type = 'select'
            choices = [{'id': k, 'text': v} for k, v in field.choices]
        elif isinstance(field, models.CharField):
            field_type = 'text'
            value = request.GET.get(name)
        elif isinstance(field, models.BooleanField):
            field_type = 'boolean'
            value = request.GET.get(name)
            if value:
                value = value == 'true'
        elif isinstance(field, models.DateField):
            field_type = 'text' if suffix in ('year', 'month') else 'date'
        elif isinstance(field, models.ForeignKey):
            field_type = 'select'
            value = request.GET.get(name)
            if value:
                value = dict(id=value, text=request.GET.get(f'{name}__autocomplete'))
        elif isinstance(field, models.ManyToManyField):
            field_type = 'select'
        return dict(name=name, type=field_type, value=value, label=field.verbose_name)
    return None


class PageNumberPagination(pagination.PageNumberPagination):
    page_size = 10

    def __init__(self, *args, **kwargs):
        self.url = None
        self.model = None
        self.relation_name = None
        self.context = None
        self.instances = []
        self.original_queryset = None
        self.calendar = None
        super().__init__(*args, **kwargs)

    def paginate_queryset(self, queryset, request, view=None, relation_name=None):
        self.original_queryset = queryset
        self.url = request.get_full_path()
        self.model = queryset.model
        self.relation_name = relation_name
        self.context = dict(request=request, view=view)
        self.subset = request.GET.get('subset')
        queryset = queryset.order_by('id') if not queryset.ordered else queryset
        key = '{}.{}'.format(self.model._meta.app_label, self.model._meta.model_name)
        item = specification.items[key]
        if item.list_calendar:
            queryset, self.calendar = to_calendar(queryset, request, item.list_calendar)
        if self.subset:
            queryset = getattr(queryset, self.subset)()
        return super().paginate_queryset(queryset, request, view=view)

    def get_link(self, page):
        params = {k:v for k, v in self.request.query_params.items()}
        params.update(page=page)
        return "{}://{}{}?{}".format(
            self.request.META.get('X-Forwarded-Proto', self.request.scheme), self.request.get_host(),
            self.request.path, '&'.join([f'{k}={v}' for k, v in params.items()])
        ) if page else None

    def get_next_link(self):
        return self.get_link(self.page.next_page_number()) if self.page.has_next() else None

    def get_previous_link(self):
        return self.get_link(self.page.previous_page_number()) if self.page.has_previous() else None

    def get_paginated_response(self, data, metadata=None, keep_path=False):
        relation_name = self.relation_name
        key = '{}.{}'.format(self.model._meta.app_label, self.model._meta.model_name)
        item = specification.items[key]
        title = self.model._meta.verbose_name_plural
        base_url = self.context['request'].path if keep_path else '/api/v1/{}/'.format(item.prefix)
        actions = []
        filters = []
        search = []
        subsets = {}
        aggregations = {}
        if metadata:
            title = metadata.get('title') or title
            relation_name = metadata.get('name') or relation_name
            if relation_name:
                relation_name = relation_name[4:] if relation_name.startswith('get_') else relation_name
            actions.extend(actions_metadata(data, metadata.get('actions', {}), self.context, base_url, self.instances, viewer=metadata.get('viewer')))
            related_field = metadata.get('related_field')
            if related_field:
                url = '{}{}/add/'.format(self.context['request'].path, metadata['name'])
                actions.append(dict(name='append', url=url, icon='plus', target='queryset', modal=True, ids=[]))

            for name in metadata.get('search', ()):
                search.append(name)

            for lookup in metadata.get('filters', ()):
                field = filter_field(self.model, lookup, self.context['request'])
                if field:
                    filters.append(field)

            for name in metadata.get('subsets', ()):
                subsets[name] = getattr(self.original_queryset, name)().count()

            for name in metadata.get('aggregations', ()):
                api_name = name[4:] if name.startswith('get_') else name
                aggregations[api_name] = getattr(self.original_queryset, name)()
                if isinstance(aggregations[api_name], Decimal):
                    aggregations[api_name] = str(aggregations[api_name]).replace('.', ',')

        response = super().get_paginated_response(data)
        model_name = to_snake_case(self.model.__name__)
        response.data.update(type='queryset', model=model_name, title=title, icon=item.icon, url=self.url, actions=actions, filters=filters, search=search, relation=self.relation_name)
        if self.calendar:
            response.data.update(calendar=self.calendar)
            response.data['filters'].extend([
                {'name': '{}__day'.format(self.calendar['field']), 'type': 'hidden', 'value': self.calendar['day']},
                {'name': '{}__month'.format(self.calendar['field']), 'type': 'hidden', 'value': self.calendar['month']},
                {'name': '{}__year'.format(self.calendar['field']), 'type': 'hidden', 'value': self.calendar['year']}
            ])
        if subsets:
            response.data.update(subsets=subsets, subset=self.context['request'].GET.get('subset'))
        if aggregations:
            response.data.update(aggregations=aggregations)

        if relation_name:
            for k in ['next', 'previous']:
                if response.data[k]:
                    if 'only=' not in response.data[k]:
                        response.data[k] = '{}&only={}'.format(response.data[k], relation_name)
        return response


class RelationPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_query_param = 'relation_page'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PaginableManyRelatedField(relations.ManyRelatedField):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginator = None
        self.relation = None

    def check_choices_response(self):
        if self.source_attrs[0] == self.context['request'].GET.get('only'):
            choices = to_choices(self.child_relation.queryset, self.context['request'])
            if choices:
                raise JsonResponseReadyException(choices)

    def get_attribute(self, instance):
        model = type(instance)
        key = '{}.{}'.format(model._meta.app_label, model._meta.model_name)
        item = specification.items.get(key)
        self.relation = item.relations.get(self.source_attrs[0])
        self.child_relation.relation_name = self.source_attrs[0]
        queryset = super().get_attribute(instance)
        if isinstance(queryset, models.QuerySet):
            self.paginator = RelationPageNumberPagination()
            if self.context['view'].action == 'retrieve' or self.source_attrs[0] == self.context['request'].GET.get('only'):
                for backend in list(self.context['view'].filter_backends):
                    queryset = backend().filter_queryset(self.context['request'], queryset, self)
            queryset = self.paginator.paginate_queryset(queryset, self.context['request'], self.context['view'], relation_name=self.source_attrs[0])

        return queryset

    def to_representation(self, value):
        if self.relation and not permissions.check_roles(self.relation.get('requires'), self.context['request'].user, False):
            data = NONE
        if self.context['view'].action in ['update']:
            data = [obj.pk for obj in value]
        elif self.relation is None and self.context['view'].action in ['list', 'retrieve']:
            if specification.app:
                data = [str(obj) for obj in value]
            else:
                data = [dict(id=obj.id, text=str(obj)) for obj in value]
        else:
            data = super().to_representation(value)
            if self.paginator:
                self.paginator.instances = [obj for obj in value]
                return self.paginator.get_paginated_response(data, self.relation).data
        return data

    def get_choices(self, cutoff=None):
        if self.relation:
            return {obj.id: str(obj) for obj in getattr(self.root.instance, self.relation['name']).all()}
        return {}