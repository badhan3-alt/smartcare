from django.db import migrations, models


def grandfather_active_accounts(apps, schema_editor):
    profile = apps.get_model('accounts', 'UserProfile')
    profile.objects.using(schema_editor.connection.alias).filter(
        user__is_active=True,
    ).update(email_verified=True)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0008_hospitalprofile')]

    operations = [
        migrations.AddField(
            model_name='userprofile', name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(grandfather_active_accounts, migrations.RunPython.noop),
    ]
