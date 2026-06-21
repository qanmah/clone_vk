from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0020_postlike_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="postcomment",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="replies",
                to="users.postcomment",
            ),
        ),
    ]
