import re
import os.path

import yaml
from django.conf import settings


class API:

    _instance = None

    def __init__(self):
        self.items = {}
        with open('api.yml') as file:
            content = file.read()
            for variable in re.findall(r'\$[a-zA-z0-9_]+', content):
                content = content.replace(variable, os.environ.get(variable[1:], ''))
        data = yaml.safe_load(content).get('api')
        for k, v in data.get('models').items():
            v = {} if v is None else v
            name = k.split('.')[-1]
            icon = v.get('icon')
            prefix = v.get('prefix', name)
            lookups = to_lookups_dict(v)
            endpoints = v.get('endpoints', dict(list={}, add={}, edit={}, delete={}, view={}))
            list_lookups = to_lookups_dict(endpoints.get('list', {}))
            view_lookups = to_lookups_dict(endpoints.get('view', {}))
            add_lookups = to_lookups_dict(endpoints.get('add', {}))
            edit_lookups = to_lookups_dict(endpoints.get('edit', {}))
            delete_lookups = to_lookups_dict(endpoints.get('delete', {}))
            item = Item(dict(
                icon = icon,
                actions=set(),
                prefix = prefix,
                url = '/api/v1/{}/'.format(prefix),
                entrypoint = str_to_list(v.get('entrypoint')),
                filters = str_to_list(v.get('filters')),
                search = to_search_list(v.get('search')),
                ordering = str_to_list(v.get('ordering')),
                fieldsets = to_fieldset_dict(v.get('fieldsets', {})),
                relations = to_relation_dict(v.get('relations', {})),
                add_fields = to_fields(endpoints.get('add', {})),
                add_fieldsets = to_fieldsets(endpoints.get('add', {})),
                edit_fields=to_fields(endpoints.get('edit', {})),
                edit_fieldsets=to_fieldsets(endpoints.get('edit', {})),
                list_display = to_fields(endpoints.get('list', {}), id_required=True),
                list_subsets = to_subsets(endpoints.get('list', {})),
                list_aggregations = to_aggregations(endpoints.get('list', {})),
                list_calendar = to_calendar(endpoints.get('list', {})),
                view_fields = to_fields(endpoints.get('view', {})),
                list_actions = to_action_list(endpoints.get('list', {}), add_default=True),
                view_actions = to_action_list(endpoints.get('view', {})),
                roles = to_roles_dict(v.get('roles', {})),

                list_lookups = list_lookups or lookups,
                view_lookups = view_lookups or lookups,
                add_lookups = add_lookups or lookups,
                edit_lookups = edit_lookups or add_lookups or lookups,
                delete_lookups = delete_lookups or lookups,
            ))
            item.view_methods = [
                name for name in (item.view_fields + item.list_display) if name.startswith('get_')
            ]
            item.view_fields = [name[4:] if name.startswith('get_') else name for name in item.view_fields]
            item.list_display = [name[4:] if name.startswith('get_') else name for name in item.list_display]
            self.items[k] = item

        self.app = data.get('app') and not os.path.exists('/opt/pnp')
        self.title = data.get('title')
        self.subtitle = data.get('subtitle')
        self.icon = data.get('icon')
        self.logo = data.get('logo')
        self.footer = data.get('footer', {})
        self.theme = data.get('theme', {})
        self.oauth = data.get('oauth', {})
        self.index = str_to_list(data.get('index'))
        self.groups = data.get('groups', {})
        self.dashboard_actions = to_action_list(data, key='dashboard')
        if self.app:
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
    return [name.strip() for name in s.split(',')] if s else []

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
            return []
        else:
            return str_to_list(value.get('subsets'))
    return []

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
    for k, v in value.items():
        roles[k] = v
    return roles

def to_calendar(value):
    if isinstance(value, dict):
        return value.get('calendar')

def to_relation_dict(value):
    for k, relation in value.items():
        if relation is None:
            value[k] = dict(name=k, fields=[], filters=[], actions={}, related_field=None, aggregations=())
        elif isinstance(relation, str):
            value[k] = dict(name=k, fields=str_to_list(relation), filters=[], actions={}, related_field=None, aggregations=())
        else:
            relation['actions'] = to_action_list(relation)
            relation['search'] = to_search_list(relation['search']) if 'search' in relation else []
            relation['subsets'] = str_to_list(relation['subsets']) if 'subsets' in relation else []
            relation['aggregations'] = str_to_list(relation['aggregations']) if 'aggregations' in relation else []
            relation['name'] = relation.get('name', k)
            relation['related_field'] = relation.get('related_field')
            for key in ['fields', 'filters']:
                relation[key] = str_to_list(relation[key]) if key in relation else []
        if 'id' not in value[k]['fields']:
            value[k]['fields'].insert(0, 'id')
        if 'id' not in value[k]['filters']:
            value[k]['filters'].insert(0, 'id')
    return value

def to_fieldset_dict(value):
    for k, v in value.items():
        if isinstance(v, str):
            value[k] = dict(name=k, fields=str_to_list(v))
        else:
            v['name'] = k
            if 'fields' in v:
                v['fields'] = str_to_list(v['fields'])
    return value


def to_lookups_dict(value):
    if isinstance(value, dict):
        requires = value.get('requires') or {}
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
    return {}

