from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0015_post_feed_improvements"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("public", "Всем"),
                    ("followers", "Подписчикам"),
                    ("private", "Только мне"),
                ],
                default="public",
                max_length=12,
            ),
        ),
    ]
