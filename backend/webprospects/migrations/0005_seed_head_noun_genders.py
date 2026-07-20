from django.core.management import call_command
from django.db import migrations


def seed_head_noun_genders(apps, schema_editor):
    """Load the head-noun gender fixture, but only on a fresh install (empty
    table), so admin edits are never overwritten on later deploys."""
    HeadNounGender = apps.get_model("webprospects", "HeadNounGender")
    if HeadNounGender.objects.exists():
        return
    call_command("loaddata", "head_noun_genders", app_label="webprospects")


def unseed(apps, schema_editor):
    # No-op: we don't delete data on reverse (avoid destroying admin edits).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("webprospects", "0004_headnoungender"),
    ]

    operations = [
        migrations.RunPython(seed_head_noun_genders, unseed),
    ]
