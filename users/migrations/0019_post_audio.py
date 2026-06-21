import users.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0018_post_photos"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="audio",
            field=models.FileField(blank=True, null=True, upload_to=users.models.post_audio_path),
        ),
    ]
