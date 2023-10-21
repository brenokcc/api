from django.contrib.auth.models import User, Group
from django.conf import settings
from .models import Role
from .utils import related_model


def post_save_func(sender, **kwargs):
    pk = kwargs['instance'].pk
    model = '{}.{}'.format(sender._meta.app_label, sender._meta.model_name)
    for name, role in sender.__roles__.items():
        for username in sender.objects.filter(pk=pk).values_list(role['username'], flat=True):
            if username is None:
                for scope in role.get('scopes', {}).keys():
                    Role.objects.filter(
                        name=name, scope=scope, model=model, value=pk
                    ).delete()
            else:
                user = User.objects.filter(username=username).first()
                if user is None:
                    user = User.objects.create(username=username)
                    user.set_password(settings.DEFAULT_PASSWORD(user))
                    user.save()
                if role.get('scopes'):
                    for scope, lookup in role.get('scopes').items():
                        scope_model = sender if lookup in ('id', 'pk') else related_model(sender, lookup)
                        model = '{}.{}'.format(scope_model._meta.app_label, scope_model._meta.model_name)
                        for value in sender.objects.filter(pk=pk).values_list(lookup, flat=True):
                            Role.objects.get_or_create(
                                username=username, name=name, model=model, scope=scope, value=value
                            )
                else:
                    Role.objects.get_or_create(
                        username=username, name=name, model=None, scope=None, value=None
                    )


def m2m_save_func(sender, **kwargs):
    if kwargs['action'] in ('pre_add', 'pre_remove'):
        pass
    else:
        post_save_func(type(kwargs['instance']), instance=kwargs['instance'])


def post_delete_func(sender, **kwargs):
    pk = kwargs['instance'].pk
    model = '{}.{}'.format(sender._meta.app_label, sender._meta.model_name)
    Role.objects.filter(model=model, value=pk).delete()
