import re
import operator
from datetime import datetime, date, timedelta
from django.db import models
from functools import reduce
from inspect import isfunction
from django.db.models.aggregates import Count
from django.db.models.fields import related_descriptors
from django.db import models


def as_choices(qs, limit=20):
    return [{'id': value.pk, 'text': str(value)} for value in qs[0:limit]]


def to_choices(queryset, request, relation_name=None, limit_choices=True):
    from .actions import ACTIONS
    field_name = request.query_params.get('choices_field')
    if field_name:
        if relation_name:
            if '.' in relation_name:
                queryset = ACTIONS[relation_name](context=dict(request=request)).view()
            elif relation_name.startswith('get_'):
                queryset = getattr(queryset.first(), relation_name)()
            else:
                queryset = getattr(queryset.first(), relation_name)
        model = queryset.model
        term = request.query_params.get('choices_search')
        field = model.get_field(field_name)
        if field.related_model:
            if limit_choices:
                pks = queryset.values_list(field_name, flat=True)
                qs = field.related_model.objects.filter(pk__in=pks)
            else:
                qs = field.related_model.objects
            return as_choices(qs.apply_search(term))
        else:
            return [{'id': choice[0], 'text': choice[1]} for choice in field.choices]
    return None


def related_model(model, relation_name):
 attr = getattr(model, relation_name, None)
 if attr is None or relation_name.startswith('get_'):
  if relation_name.startswith('get_'):
      attr = getattr(model, relation_name)
  else:
      attr = getattr(model, f'get_{relation_name}')
  value = attr(model(id=0))
  if isinstance(value, models.QuerySet):
    return value.model
  elif isinstance(value, models.Model):
    return type(value)
 if isinstance(attr, related_descriptors.ForwardManyToOneDescriptor):
    return attr.field.related_model
 elif isinstance(attr, related_descriptors.ManyToManyDescriptor):
    return attr.field.related_model
 elif isinstance(attr, related_descriptors.ReverseManyToOneDescriptor):
    return attr.rel.related_model


def to_snake_case(name):
    return name if name.islower() else re.sub(r'(?<!^)(?=[A-Z0-9])', '_', name).lower()


def to_camel_case(name):
    return ''.join(word.title() for word in name.split('_'))


def to_calendar(qs, request, attr_name):
    day = request.GET.get(f'{attr_name}__day')
    month = request.GET.get(f'{attr_name}__month')
    year = request.GET.get(f'{attr_name}__year')
    if month and year:
        start = date(int(year), int(month), 1)
    else:
        start = qs.order_by(attr_name).values_list(attr_name, flat=True).first() or date.today()
        month = start.month
        year = start.year
    current = date(start.year, start.month, 1)
    qs = qs.filter(**{f'{attr_name}__year': start.year, f'{attr_name}__month': start.month})
    total = {}
    for key in qs.values_list(attr_name, flat=True):
        key = key.strftime('%d/%m/%Y')
        if key not in total:
            total[key] = 0
        total[key] += 1
    if day:
        qs = qs.filter(**{f'{attr_name}__day': day})
    next = current + timedelta(days=31)
    previous = current + timedelta(days=-31)
    return qs, dict(
        field=attr_name, total=total,
        day=day, month=month, year=year, next=dict(month=next.month, year=next.year),
        previous=dict(month=previous.month, year=previous.year)
    )