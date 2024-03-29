import sys
from django.db import models
from django.apps import apps
from datetime import datetime
from api.specification import API
from django.conf import settings
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives


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

    class Meta:
        verbose_name = 'Papel'
        verbose_name_plural = 'Papéis'

    def __str__(self):
        return self.get_description()

    def get_verbose_name(self):
        specification = API.instance()
        return specification.groups.get(self.name, self.name)

    def get_scope_value(self):
        return apps.get_model(self.model).objects.get(pk=self.value) if self.model else None

    def get_description(self):
        scope_value = self.get_scope_value()
        return '{} - {}'.format(self.get_verbose_name(), scope_value) if scope_value else self.get_verbose_name()


class EmailManager(models.Manager):
    def all(self):
        return self.order_by('-id')

    def send(self, to, subject, content, from_email=None):
        to = [to] if isinstance(to, str) else list(to)
        return self.create(from_email=from_email or 'no-replay@mail.com', to=', '.join(to), subject=subject, content=content)


class PushSubscription(models.Model):
    user = models.ForeignKey('auth.user', verbose_name='Usuário', on_delete=models.CASCADE)
    device = models.CharField(verbose_name='Dispositivo')
    data = models.JSONField(verbose_name='Dados da Inscrição')

    class Meta:
        verbose_name = 'Inscrição de Notificação'
        verbose_name_plural = 'Inscrições de Notificação'

    def notify(self, text):
        import os
        from pywebpush import webpush
        specification = API.instance()
        response = webpush(
            subscription_info=self.data, data='{}>>>{}'.format(specification.title, text),
            vapid_private_key=os.environ.get('VAPID_PRIVATE_KEY'),
            vapid_claims={"sub": "mailto:admin@admin.com"}
        )
        return response.status_code == 201


class Error(models.Model):
    user = models.OneToOneField('auth.user', verbose_name='Usuário', on_delete=models.CASCADE, null=True)
    date = models.DateTimeField('Data/Hora')
    traceback = models.TextField('Rastreamento')

    class Meta:
        verbose_name = 'Erro'
        verbose_name_plural = 'Erros'


class Email(models.Model):
    from_email = models.EmailField('Remetente')
    to = models.TextField('Destinatário', help_text='Separar endereços de e-mail por ",".')
    subject = models.CharField('Assunto')
    content = models.TextField('Conteúdo', formatted=True)
    sent_at = models.DateTimeField('Data/Hora', null=True)

    objects = EmailManager()

    class Meta:
        verbose_name = 'E-mail'
        verbose_name_plural = 'E-mails'

    def __str__(self):
        return self.subject

    def save(self, *args, **kwargs):
        to = [email.strip() for email in self.to.split(',')]
        msg = EmailMultiAlternatives(self.subject, strip_tags(self.content), self.from_email, to)
        msg.attach_alternative(self.content, "text/html")
        if self.sent_at is None:
            msg.send(fail_silently=True)
            self.sent_at = datetime.now()
        super().save(*args, **kwargs)
