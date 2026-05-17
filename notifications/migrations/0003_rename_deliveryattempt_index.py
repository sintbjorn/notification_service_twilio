from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_alter_notification_status"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="deliveryattempt",
            old_name="notificat_notification_channel_created_at_idx",
            new_name="notificatio_notific_66e0c2_idx",
        ),
    ]
