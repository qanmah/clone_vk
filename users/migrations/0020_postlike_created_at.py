from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0019_post_audio"),
    ]

    operations = [
        migrations.AddField(
            model_name="postlike",
            name="created_at",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="postlike",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
