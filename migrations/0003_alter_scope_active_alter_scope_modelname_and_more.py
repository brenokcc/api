# Generated by Django 4.2.4 on 2023-09-16 11:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_scope_active'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scope',
            name='active',
            field=models.BooleanField(default=True, null=True, verbose_name='Active'),
        ),
        migrations.AlterField(
            model_name='scope',
            name='modelname',
            field=models.CharField(db_index=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='scope',
            name='scopename',
            field=models.CharField(db_index=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='scope',
            name='value',
            field=models.IntegerField(db_index=True, null=True, verbose_name='Value'),
        ),
    ]
