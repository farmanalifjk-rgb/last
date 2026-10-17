# Generated for DI API v1.12 (2025-07-24) — PRAL as licensed integrator
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fbr', '0001_initial'),
    ]

    operations = [
        # Province reference (5.1)
        migrations.CreateModel(
            name='FBRProvince',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='PRAL provinceId or name, e.g. Sindh', max_length=64, unique=True)),
                ('description', models.CharField(blank=True, max_length=128)),
            ],
            options={'ordering': ['code']},
        ),
        # HS code: allow dotted 0101.2100
        migrations.AlterField(
            model_name='fbrhscode',
            name='code',
            field=models.CharField(max_length=9, unique=True, validators=[django.core.validators.RegexValidator('^(\\d{8}|\\d{4}\\.\\d{4})$', message='HS code must be 8 digits or dotted 0101.2100')]),
        ),
        # FBRConfiguration new fields for v1.12
        migrations.AddField(
            model_name='fbrconfiguration',
            name='seller_province',
            field=models.ForeignKey(blank=True, help_text='Seller province (5.1) — required for v1.12', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='seller_configurations', to='fbr.fbrprovince'),
        ),
        migrations.AddField(
            model_name='fbrconfiguration',
            name='seller_province_text',
            field=models.CharField(blank=True, help_text='Free-form province name if not using FK (legacy data)', max_length=64),
        ),
        migrations.AddField(
            model_name='fbrconfiguration',
            name='scenario_id',
            field=models.CharField(blank=True, choices=[('SN001', 'SN001'), ('SN002', 'SN002'), ('SN003', 'SN003'), ('SN004', 'SN004'), ('SN005', 'SN005'), ('SN006', 'SN006'), ('SN007', 'SN007'), ('SN008', 'SN008'), ('SN009', 'SN009'), ('SN010', 'SN010'), ('SN011', 'SN011'), ('SN012', 'SN012'), ('SN013', 'SN013'), ('SN014', 'SN014'), ('SN015', 'SN015'), ('SN016', 'SN016'), ('SN017', 'SN017'), ('SN018', 'SN018'), ('SN019', 'SN019'), ('SN020', 'SN020'), ('SN021', 'SN021'), ('SN022', 'SN022'), ('SN023', 'SN023'), ('SN024', 'SN024'), ('SN025', 'SN025'), ('SN026', 'SN026'), ('SN027', 'SN027'), ('SN028', 'SN028')], help_text='Sandbox scenarioId SN001..SN028 (v1.12 §9, required for sandbox)', max_length=6),
        ),
        migrations.AddField(
            model_name='fbrconfiguration',
            name='integrator',
            field=models.CharField(choices=[('pral', 'PRAL (licensed integrator)')], default='pral', help_text='Licensed integrator (default PRAL)', max_length=20),
        ),
        # FBRBuyerProfile new fields
        migrations.AddField(
            model_name='fbrbuyerprofile',
            name='buyer_province',
            field=models.ForeignKey(blank=True, help_text='Buyer province (5.1) — required for v1.12', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='buyer_profiles', to='fbr.fbrprovince'),
        ),
        migrations.AddField(
            model_name='fbrbuyerprofile',
            name='buyer_province_text',
            field=models.CharField(blank=True, help_text='Free-form province if not using FK', max_length=64),
        ),
        migrations.AddField(
            model_name='fbrbuyerprofile',
            name='buyer_registration_type',
            field=models.CharField(choices=[('Registered', 'Registered'), ('Unregistered', 'Unregistered')], default='Registered', help_text='Registered / Unregistered (v1.12 p10)', max_length=12),
        ),
        migrations.AlterField(
            model_name='fbrbuyerprofile',
            name='ntn_cnic',
            field=models.CharField(blank=True, help_text='Blank allowed if buyerRegistrationType=Unregistered (v1.12 p10)', max_length=20),
        ),
        # FBRProductProfile new field
        migrations.AddField(
            model_name='fbrproductprofile',
            name='sro_item_serial_no',
            field=models.CharField(blank=True, help_text='sroItemSerialNo (v1.12 5.10) — optional', max_length=30),
        ),
        # FBRSubmission new fields for v1.12 response
        migrations.AddField(
            model_name='fbrsubmission',
            name='error_code',
            field=models.CharField(blank=True, help_text='errorCode 0001.. (v1.12 §7)', max_length=10),
        ),
        migrations.AddField(
            model_name='fbrsubmission',
            name='validation_response',
            field=models.JSONField(blank=True, default=dict, help_text='validationResponse object (v1.12)'),
        ),
        migrations.AddField(
            model_name='fbrsubmission',
            name='is_validate',
            field=models.BooleanField(default=False, help_text='True if this was a validateinvoicedata call (dry-run)'),
        ),
        migrations.AddField(
            model_name='fbrsubmission',
            name='invoice_ref_no',
            field=models.CharField(blank=True, help_text='invoiceRefNo for debit notes (v1.12)', max_length=64),
        ),
        migrations.AddField(
            model_name='fbrsubmission',
            name='status_code_legacy',
            field=models.IntegerField(blank=True, help_text='Legacy integer statusCode', null=True),
        ),
        migrations.AlterField(
            model_name='fbrsubmission',
            name='status_code',
            field=models.CharField(blank=True, help_text='statusCode string 00/01 (v1.12) or 200 (v1.0)', max_length=10),
        ),
        # Fix constraint to exclude validate submissions (is_validate=False)
        migrations.RemoveConstraint(
            model_name='fbrsubmission',
            name='unique_accepted_fbr_submission_per_invoice',
        ),
        migrations.AddConstraint(
            model_name='fbrsubmission',
            constraint=models.UniqueConstraint(condition=models.Q(('is_validate', False), ('status', 'accepted')), fields=('invoice',), name='unique_accepted_fbr_submission_per_invoice'),
        ),
    ]
