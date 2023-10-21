from rest_framework import exceptions
from .models import Role


def check_roles(lookups, user, raise_exception=True):
    if lookups is None:
        checked = True
    elif user.is_superuser:
        checked = True
    else:
        names = [k for k in lookups.keys()]
        if names:
            checked = None in names or Role.objects.filter(username=user.username, name__in=names).exists()
        else:
            checked = False
    if raise_exception and not checked:
        raise exceptions.PermissionDenied('You do not have permission to perform this action.', 403)
    return checked

def check_lookups(instance, lookups, user, raise_exception=True):
    queryset = type(instance).objects.filter(pk=instance.pk) if hasattr(instance, 'pk') else instance
    checked = user.is_superuser or apply_lookups(queryset, lookups, user).exists()
    if raise_exception and not checked:
        raise exceptions.PermissionDenied('You do not have permission to perform this action.', 403)
    return checked

def apply_lookups(queryset, lookups, user):
    if user.is_superuser:
        return queryset
    qs = queryset.none()
    roles = Role.objects.filter(username=user.username, active=True)
    role_names = set(roles.values_list('name', flat=True).distinct())
    role_names.add(None)
    for role_name, lookup in lookups.items():
        if role_name in role_names:
            if lookup:
                for scope_lookup, scopename in lookup.items():
                    if scopename == 'username':
                        kwargs = {scope_lookup: user.username}
                    else:
                        pks = roles.filter(scope=scopename).values_list('value', flat=True)
                        kwargs = {'{}__in'.format(scope_lookup): pks}
                    qs = qs | queryset.filter(**kwargs)
            else:
                qs = queryset
                break
    return qs