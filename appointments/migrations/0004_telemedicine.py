import uuid
from django.db import migrations, models


def _populate_telemedicine_rooms(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    for appointment in Appointment.objects.filter(telemedicine_room__isnull=True).iterator():
        appointment.telemedicine_room = uuid.uuid4()
        appointment.save(update_fields=['telemedicine_room'])


class Migration(migrations.Migration):
    dependencies = [('appointments', '0003_appointment_reminder_24h_sent_and_more')]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='telemedicine_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='appointment',
            name='telemedicine_room',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(
            code=_populate_telemedicine_rooms,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='appointment',
            name='telemedicine_room',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
