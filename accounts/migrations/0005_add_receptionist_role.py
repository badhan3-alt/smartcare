from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_alter_userprofile_phone'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('patient', 'Patient'),
                    ('doctor', 'Doctor'),
                    ('receptionist', 'Receptionist'),
                ],
                default='patient',
                max_length=20,
            ),
        ),
    ]
