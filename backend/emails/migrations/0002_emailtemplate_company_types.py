from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("emails", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailtemplate",
            name="company_types",
            field=models.ManyToManyField(
                related_name="templates",
                to="emails.companytype",
            ),
        ),
    ]
