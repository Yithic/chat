from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_app', '0002_message_reply_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='media_content_type',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='message',
            name='media_file_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
