from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("emails", "0003_copy_company_type_to_m2m"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="emailtemplate",
            name="company_type",
        ),
    ]
