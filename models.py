from django.db import models
from django.apps import apps
from api.specification import API

api = API.instance()


class RoleQuerySet(models.QuerySet):

    def contains(self, *names):
        _names = getattr(self, '_names', None)
        if _names is None:
            _names = set(self.filter(name__in=names, active=True).values_list('name', flat=True))
            setattr(self, '_names', _names)
        for name in names:
            if name in _names:
                return True
        return False

    def active(self):
        return self.filter(active=True)

    def inactive(self):
        return self.filter(active=False)


class Role(models.Model):
    username = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=50, db_index=True)
    scope = models.CharField(max_length=50, db_index=True, null=True)
    model = models.CharField(max_length=50, db_index=True, null=True)
    value = models.IntegerField('Value', db_index=True, null=True)
    active = models.BooleanField('Active', default=True, null=True)

    objects = RoleQuerySet()

    def __str__(self):
        return self.get_description()

    def get_verbose_name(self):
        return api.groups.get(self.name, self.name)

    def get_scope_value(self):
        return apps.get_model(self.model).objects.get(pk=self.value) if self.model else None

    def get_description(self):
        scope_value = self.get_scope_value()
        return '{} - {}'.format(self.get_verbose_name(), scope_value) if scope_value else self.get_verbose_name()
