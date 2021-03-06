# Generated by Django 3.0.2 on 2020-04-18 17:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='series',
            old_name='city_id',
            new_name='city',
        ),
        migrations.AlterUniqueTogether(
            name='city',
            unique_together={('city', 'district')},
        ),
        migrations.AlterUniqueTogether(
            name='items',
            unique_together={('item_name',)},
        ),
    ]
