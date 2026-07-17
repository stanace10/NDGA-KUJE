from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0014_publiceventimage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="publicwebsitesettings",
            name="hero_title",
            field=models.CharField(
                default="A Leading Catholic Girls' Boarding School in Abuja",
                max_length=220,
            ),
        ),
        migrations.AlterField(
            model_name="publicwebsitesettings",
            name="hero_subtitle",
            field=models.TextField(
                default=(
                    "Focused on academic excellence, disciplined boarding, and strong Catholic character "
                    "formation for girls in a safe learning community."
                ),
            ),
        ),
    ]
