import django.db.models.deletion
import users.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0017_message_shared_post"),
    ]

    operations = [
        migrations.AlterField(
            model_name="post",
            name="video",
            field=models.FileField(blank=True, null=True, upload_to=users.models.post_video_path),
        ),
        migrations.CreateModel(
            name="PostImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to=users.models.post_image_path)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("post", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="users.post")),
            ],
            options={"ordering": ("order", "id")},
        ),
    ]
