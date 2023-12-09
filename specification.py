import re
import os.path

import yaml
from django.apps import apps
from django.db import models
from django.conf import settings


class EmptyDict(dict):
 def __setitem__(self, k, v):
  raise Exception('This is a frozen empty dict.')

EMPTY_DICT = EmptyDict()

class API:

    _instance = None

    def __init__(self):
        self.items = {}
        with open('api.yml') as file:
            content = file.read()
            for variable in re.findall(r'\$[a-zA-z0-9_]+', content):
                content = content.replace(variable, os.environ.get(variable[1:], ''))
        data = yaml.safe_load(content).get('api')
        self.menu = to_menu_items([], data.get('menu', {}))
        # import pprint; pprint.pprint(self.menu)
        for k, v in data.get('models').items():
            model = apps.get_model(k)
            relation_field_names = []
            for field in model._meta.get_fields():
                if isinstance(field, models.ForeignKey) or isinstance(field, models.ManyToManyField):
                    relation_field_names.append(field.name)
            for ro in model._meta.related_objects:
                relation_field_names.append(ro.get_accessor_name())

            v = {} if v is None else v
            name = k.split('.')[-1]
            icon = v.get('icon')
            prefix = v.get('prefix', name)
            lookups = to_lookups_dict(v)
            endpoints = v.get(
                'endpoints', dict(list=EMPTY_DICT, add=EMPTY_DICT, edit=EMPTY_DICT, delete=EMPTY_DICT, view=EMPTY_DICT)
            )
            list_lookups = to_lookups_dict(endpoints.get('list'))
            view_lookups = to_lookups_dict(endpoints.get('view'))
            add_lookups = to_lookups_dict(endpoints.get('add'))
            edit_lookups = to_lookups_dict(endpoints.get('edit'))
            delete_lookups = to_lookups_dict(endpoints.get('delete'))
            item = Item(dict(
                icon = icon,
                actions = set(str_to_list(v.get('actions'))),
                prefix = prefix,
                url = '/api/{}/'.format(prefix),
                entrypoint = str_to_list(v.get('entrypoint')),
                filters = str_to_list(v.get('filters')),
                search = to_search_list(v.get('search')),
                ordering = str_to_list(v.get('ordering')),
                relations = {},
                related_fieldsets = {},
                add_fieldsets = to_fieldset_dict(endpoints.get('add')),
                edit_fieldsets=to_fieldset_dict(endpoints.get('edit')),
                list_display = to_fields(endpoints.get('list'), id_required=True),
                list_fieldsets = to_fieldset_dict(endpoints.get('list')),
                list_subsets = to_subsets(endpoints.get('list')),
                list_aggregations = to_aggregations(endpoints.get('list')),
                list_calendar = to_calendar(endpoints.get('list')),
                view_fields = to_fieldset_dict(endpoints.get('view'), relation_field_names),
                list_actions = to_action_list(endpoints.get('list'), add_default=True),
                view_actions = to_action_list(endpoints.get('view')),
                roles = to_roles_dict(v.get('roles')),

                list_lookups = list_lookups or lookups,
                view_lookups = view_lookups or lookups,
                add_lookups = add_lookups or lookups,
                edit_lookups = edit_lookups or add_lookups or lookups,
                delete_lookups = delete_lookups or lookups,
            ))
            for x, y in item.view_fields.items():
                if x.startswith('get_') or '.' in x or x in relation_field_names:
                    item.relations[x] = y
            item.view_methods = [
                name for name in (list(item.view_fields.keys()) + item.list_display) if name.startswith('get_')
            ]
            for f in model._meta.get_fields():
                method_name = 'get_{}'.format(f.name)
                if hasattr(model, method_name):
                    item.view_methods.append(method_name)
            item.list_display = [name[4:] if name.startswith('get_') else name for name in item.list_display]
            self.items[k] = item

        self.app = data.get('app') and not os.path.exists('/opt/pnp')
        self.title = data.get('title')
        self.subtitle = data.get('subtitle')
        self.icon = data.get('icon')
        self.logo = data.get('logo')
        self.footer = data.get('footer', EMPTY_DICT)
        self.theme = data.get('theme', EMPTY_DICT)
        self.oauth = data.get('oauth', EMPTY_DICT)
        self.index = str_to_list(data.get('index'))
        self.groups = data.get('groups', EMPTY_DICT)
        self.dashboard_actions = to_action_list(data, key='dashboard')
        if self.app and not os.path.exists('/app'):
            # settings.MIDDLEWARE.append('api.middleware.AppMiddleware')
            settings.MIDDLEWARE.append('api.middleware.ReactJsMiddleware')
        settings.MIDDLEWARE.append('api.middleware.CorsMiddleware')

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = API()
        return cls._instance

    def getitem(self, model):
        return self.items['{}.{}'.format(model._meta.app_label, model._meta.model_name)]



class Item(object):
    def __init__(self, d):
        self.__dict__ = d


def to_action_list(value, key='actions', add_default=False):
    if isinstance(value, dict) and value.get(key):
        actions = str_to_list(value.get(key))
    else:
        actions = []
    if add_default and not actions:
        actions = ['add', 'view', 'edit', 'delete']
    return actions

def str_to_list(s, id_required=False):
    return [name.strip() for name in s.replace(',', '').replace('  ', ' ').split()] if s else []

def to_search_list(s):
    return [(f'{lookup}__icontains' if 'exact' not in lookup else lookup) for lookup in str_to_list(s)]

def iter_to_list(i):
    return [o for o in i]

def to_aggregations(value):
    if value:
        if isinstance(value, str):
            return []
        else:
            return str_to_list(value.get('aggregations'))
    return []

def to_subsets(value):
    if value:
        if isinstance(value, str):
            return {}
        else:
            return {k1: to_relation_dict(k1, v1) for k1, v1 in value.get('subsets', {}).items()}
    return {}

def to_fields(value, id_required=False):
    if value:
        if isinstance(value, str):
            l = str_to_list(value)
        else:
            l = str_to_list(value.get('fields'))
    else:
        l = []
    if l and id_required and 'id' not in l:
        l.insert(0, 'id')
    return l

def to_fieldsets(value):
    if value:
        if isinstance(value, dict):
            fieldsets = {}
            for k, v in value.get('fieldsets', {}).items():
                fieldsets[k] = str_to_list(v)
            return fieldsets
    return {}

def to_roles_dict(value):
    roles = {}
    if value:
        for k, v in value.items():
            roles[k] = v
    return roles

def to_calendar(value):
    if isinstance(value, dict):
        return value.get('calendar')

def to_relation_dict(k, v):
    if v is None:
        relation = dict(name=k, fields={}, filters=[], actions={}, related_field=None, aggregations=())
    elif isinstance(v, str):
        relation = dict(name=k, fields={name: width for name, width in str_to_width_list(v)}, filters=[], actions={}, related_field=None, aggregations=())
    else:
        relation = {}
        relation['actions'] = to_action_list(v)
        relation['search'] = to_search_list(v['search']) if 'search' in v else []
        relation['subsets'] = {k1: to_relation_dict(k1, v1) for k1, v1 in v['subsets'].items()} if 'subsets' in v else {}
        relation['aggregations'] = str_to_list(v['aggregations']) if 'aggregations' in v else []
        relation['name'] = v.get('name', k)
        relation['requires'] = v.get('requires')
        relation['related_field'] = v.get('related_field')
        relation['filters'] = str_to_list(v['filters']) if 'filters' in v else []
        relation['fields'] = {name: width for name, width in str_to_width_list(v.get('fields'))}
        if 'fieldsets' in v:
            relation['fieldsets'] = to_fieldset_dict(v)
            if not relation['fields']:
                for item in relation['fieldsets'].values():
                    relation['fields'].update(item['fields'])
    if 'id' not in relation['fields']:
        relation['fields']['id'] = 100
    if 'id' not in relation['filters']:
        relation['filters'].insert(0, 'id')
    return relation

def str_to_width_list(s):
    l = []
    if s:
        s = s.strip().replace('  ', ' ')
        for l1 in [v.strip() for v in s.split(',')]:
            if ' ' in l1:
                l2 = l1.split()
                for k in l2:
                    l.append((k,  int(100/len(l2))))
            else:
                l.append((l1, 100))
    return l

def to_fieldset_dict(data, relation_field_names=()):
    fieldsets = {} if data else EMPTY_DICT
    if isinstance(data, str):
        fieldsets[''] = dict(name='', fields={name: width for name, width in str_to_width_list(data)}, requires=None, actions=[])
    elif data:
        metadata = data.get('fieldsets', data.get('fields', {}))
        if isinstance(metadata, str):
            fieldsets[''] = dict(name='', fields={name: width for name, width in str_to_width_list(metadata)}, requires=None, actions=[])
        elif metadata:
            for k, v in metadata.items():
                if k.startswith('get_') or '.' in k or k in relation_field_names:
                    fieldsets[k] = to_relation_dict(k, v)
                else:
                    if isinstance(v, str):
                        fieldsets[k] = dict(name=k, fields={name: width for name, width in str_to_width_list(v)}, requires=None, actions=[])
                    elif v:
                        fieldsets[k] = dict(name=k, fields={name: width for name, width in str_to_width_list(v['fields'])}, requires=v.get('requires'), actions=str_to_list(v.get('actions')))
    return fieldsets

def to_menu_items(menu, items):
    for item in items:
        if isinstance(item, dict):
            for k, v in item.items():
                if v:
                    subitem = dict(label=k, children=[])
                    to_menu_items(subitem['children'], v)
                    menu.append(subitem)
        else:
            subitem = dict(endpoint=item)
            menu.append(subitem)
    return menu

def to_lookups_dict(value):
    if isinstance(value, dict):
        requires = value.get('requires') or EMPTY_DICT
        lookups = {}
        if isinstance(requires, str):
            lookups[None] = {}
            for k in str_to_list(requires):
                lookups[None][k] = 'username'
        else:
            for k, v in requires.items():
                group_name = None if k == 'user' else k
                lookups[group_name] = {}
                if isinstance(v, str):
                    for lookup in str_to_list(v):
                        lookups[group_name][lookup] = 'username'
                elif v:
                    for k1, v1 in v.items():
                        lookups[group_name][k1] = v1
        return lookups
    return EMPTY_DICT

