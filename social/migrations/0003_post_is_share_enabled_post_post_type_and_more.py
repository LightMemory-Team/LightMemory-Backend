import secrets

from django.db import migrations, models

import social.models


def fill_tokens(apps, schema_editor):
    Post = apps.get_model('social', 'Post')
    for post in Post.objects.all():
        post.share_token = secrets.token_urlsafe(16)
        post.save(update_fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('social', '0002_post_diary'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='post_type',
            field=models.CharField(default='diary', max_length=20),
        ),
        migrations.AddField(
            model_name='post',
            name='is_share_enabled',
            field=models.BooleanField(default=True),
        ),
        # 1) 先加成可為空、不唯一
        migrations.AddField(
            model_name='post',
            name='share_token',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        # 2) 幫既有貼文各補一組不同的 token
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        # 3) 改成唯一、不可為空
        migrations.AlterField(
            model_name='post',
            name='share_token',
            field=models.CharField(
                default=social.models.generate_share_token,
                max_length=32,
                unique=True,
            ),
        ),
    ]