import django.db.models.deletion
import users.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0014_post_views"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="post",
            options={"ordering": ("-created_at",)},
        ),
        migrations.AlterField(
            model_name="post",
            name="video",
            field=models.FileField(upload_to=users.models.post_video_path),
        ),
        migrations.AlterField(
            model_name="postlike",
            name="post",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="likes",
                to="users.post",
            ),
        ),
        migrations.AlterField(
            model_name="postlike",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="post_likes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
