from django.core.mail import send_mail
from django.conf import settings


def send_alert_email(recipients, subject, body):
    """Send via Django SMTP. Recipients must be registered app users (enforced by SendEmail integration too)."""
    sent = send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", "pos@localhost"),
                     recipients, fail_silently=False)
    return sent > 0
