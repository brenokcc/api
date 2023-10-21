import warnings
from django.db import models
from django.db.models import manager, Q, CharField
from django.db.models.aggregates import Sum, Avg
from django.db.models.base import ModelBase
from .statistics import Statistics
from functools import reduce
import operator


warnings.filterwarnings('ignore', module='urllib3')

PROXIED_MODELS = []

class ValueSet(object):

    def __init__(self, instance, *fields, autoreload=0):
        self.instance = instance
        self.fields = fields
        self.autoreload = autoreload


class ModelMixin(object):

    @classmethod
    def get_field(cls, lookup):
        model = cls
        attrs = lookup.split('__')
        while attrs:
            attr_name = attrs.pop(0)
            if attrs:  # go deeper
                field = model._meta.get_field(attr_name)
                model = field.related_model
            else:
                try:
                    return model._meta.get_field(attr_name)
                except FieldDoesNotExist:
                    pass
        return None

    def valueset(self, *fields, autoreload=0):
        return ValueSet(self, *fields, autoreload=autoreload)

class QuerySet(models.QuerySet):

    def __init__(self, *args, **kwargs):
        self.metadata = {}
        super().__init__(*args, **kwargs)

    def count(self, x=None, y=None, title=None, chart=None):
        return Statistics(self, title=title, chart=chart).count(x=x, y=y) if x else super().count()

    def sum(self, z, x=None, y=None, title=None, chart=None):
        return Statistics(self, title=title, chart=chart).sum(z, x=x, y=y) if x else super().aggregate(sum=Sum(z))['sum'] or 0

    def _clone(self):
        qs = super()._clone()
        for k, v in self.metadata.items():
            v = self.metadata[k]
            if isinstance(v, list):
                qs.metadata[k] = list(v)
            elif isinstance(v, dict):
                qs.metadata[k] = dict(v)
            else:
                qs.metadata[k] = v
        return qs

    def fields(self, *names):
        if 'fields' not in self.metadata:
            self.metadata['fields'] = ('id',) + names
        return self

    def search(self, *names):
        if 'search' not in self.metadata:
            self.metadata['search'] = names
        return self

    def filters(self, *names):
        if 'filters' not in self.metadata:
            self.metadata['filters'] = names
        return self

    def actions(self, *names):
        if 'actions' not in self.metadata:
            self.metadata['actions'] = names
        return self

    def subsets(self, *names):
        if 'subsets' not in self.metadata:
            self.metadata['subsets'] = names
        return self

    def title(self, name):
        self.metadata['title'] = name
        return self

    def contextualize(self, request, metadata=None):
        if metadata:
            self.metadata.update(**metadata)
        filters = self.metadata.get('filters', ())
        for lookup in filters:
            if lookup in request.GET:
                self = self.apply_filter(lookup, request.GET[lookup])
        search = self.metadata.get('search', ())
        if search and 'q' in request.GET:
            self = self.apply_search(request.GET['q'], search)
        return self

    def apply_filter(self, lookup, value):
        booleans = dict(true=True, false=False, null=None)
        if len(value) == 10 and '-' in value:
            value = datetime.strptime(value, '%Y-%m-%d');
        if value in booleans:
            value = booleans[value]
        return self.filter(**{lookup: value}) if value != '' else self

    def apply_search(self, term, lookups=None):
        if lookups is None:
            lookups = [f'{field.name}__icontains' for field in self.model._meta.get_fields()
                       if isinstance(field, CharField)] or []
        if lookups:
            terms = term.split(' ') if term else []
            conditions = []
            for term in terms:
                queries = [
                    Q(**{lookup: term})
                    for lookup in lookups
                ]
                conditions.append(reduce(operator.or_, queries))

            return self.filter(reduce(operator.and_, conditions)) if conditions else self
        return self


class BaseManager(manager.BaseManager):
    def get_queryset(self):
        return super().get_queryset()

    def all(self):
        return self.get_queryset().all()


class Manager(BaseManager.from_queryset(QuerySet)):
    pass


___new___ = ModelBase.__new__


def __new__(mcs, name, bases, attrs, **kwargs):
    if attrs['__module__'] != '__fake__':
        # See .db.models.Manager
        if 'objects' in attrs and isinstance(attrs['objects'], QuerySet):
            queryset_class = attrs['objects']
            attrs.update(objects=BaseManager.from_queryset(type(queryset_class))())
        # Defining the objects Manager using .db.models.QuerySet
        if 'objects' not in attrs and not all(['objects' in dir(cls) for cls in bases]):
            attrs.update(objects=BaseManager.from_queryset(QuerySet)())

    if ModelMixin not in bases:
        bases = bases + (ModelMixin, )
    cls = ___new___(mcs, name, bases, attrs, **kwargs)
    if cls._meta.proxy_for_model:
        PROXIED_MODELS.append(cls._meta.proxy_for_model)
    return cls


ModelBase.__new__ = __new__
models.QuerySet = QuerySet
models.Manager = Manager