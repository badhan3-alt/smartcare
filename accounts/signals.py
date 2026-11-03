from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import MedicalReport


@receiver(post_delete, sender=MedicalReport)
def delete_report_file(sender, instance, using, **kwargs):
    if instance.file:
        storage = instance.file.storage
        name = instance.file.name
        # A rolled-back database deletion must leave the file available.
        transaction.on_commit(lambda: storage.delete(name), using=using, robust=True)
