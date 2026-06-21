from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0016_post_visibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="shared_post",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shared_messages",
                to="users.post",
            ),
        ),
    ]
