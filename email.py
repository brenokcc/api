from .models import Email


def send_mail(to, subject, content, from_email=None):
    Email.objects.send(to, subject, content, from_email=from_email)

