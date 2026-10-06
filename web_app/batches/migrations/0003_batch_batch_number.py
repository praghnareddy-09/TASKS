from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Q


def assign_batch_numbers(apps, schema_editor):
    Batch = apps.get_model("batches", "Batch")
    for number, batch in enumerate(Batch.objects.order_by("created_at", "pk").iterator(), start=1):
        Batch.objects.filter(pk=batch.pk).update(batch_number=number)


class Migration(migrations.Migration):

    dependencies = [
        ("batches", "0002_alter_batch_trainer"),
    ]

    operations = [
        migrations.AddField(
            model_name="batch",
            name="batch_number",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(assign_batch_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="batch",
            name="batch_number",
            field=models.PositiveIntegerField(
                help_text="For example 25",
                unique=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddConstraint(
            model_name="batch",
            constraint=models.CheckConstraint(
                condition=Q(batch_number__gt=0),
                name="batch_number_positive",
            ),
        ),
    ]
