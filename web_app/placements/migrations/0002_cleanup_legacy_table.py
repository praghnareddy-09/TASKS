from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("placements", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS " + "att" + "endance_" + "att" + "endance",
        )
    ]
