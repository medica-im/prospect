from django.db import migrations


def copy_fk_to_m2m(apps, schema_editor):
    EmailTemplate = apps.get_model("emails", "EmailTemplate")
    for template in EmailTemplate.objects.filter(company_type__isnull=False):
        template.company_types.add(template.company_type)


def copy_m2m_to_fk(apps, schema_editor):
    EmailTemplate = apps.get_model("emails", "EmailTemplate")
    for template in EmailTemplate.objects.all():
        first = template.company_types.first()
        if first:
            template.company_type = first
            template.save(update_fields=["company_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("emails", "0002_emailtemplate_company_types"),
    ]

    operations = [
        migrations.RunPython(copy_fk_to_m2m, copy_m2m_to_fk),
    ]
