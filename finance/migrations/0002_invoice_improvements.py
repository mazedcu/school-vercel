from django.db import migrations, models
import django.db.models.deletion


def populate_invoice_numbers(apps, schema_editor):
    """Set invoice_number for any existing invoices that have blank values."""
    Invoice = apps.get_model('finance', 'Invoice')
    for idx, inv in enumerate(Invoice.objects.filter(invoice_number='').order_by('id'), start=1):
        inv.invoice_number = f"LEGACY-{inv.pk:03d}"
        inv.save(update_fields=['invoice_number'])


def migrate_fee_structure_to_line_items(apps, schema_editor):
    """Convert old single fee_structure FK into InvoiceLineItem rows."""
    Invoice = apps.get_model('finance', 'Invoice')
    InvoiceLineItem = apps.get_model('finance', 'InvoiceLineItem')
    FeeStructure = apps.get_model('finance', 'FeeStructure')

    for inv in Invoice.objects.all():
        # Check if old fee_structure_id exists
        if hasattr(inv, 'fee_structure_id') and inv.fee_structure_id:
            try:
                fee = FeeStructure.objects.get(id=inv.fee_structure_id)
                InvoiceLineItem.objects.create(
                    invoice=inv,
                    fee_structure=fee,
                    description=fee.name,
                    amount=fee.amount,
                )
                # Set subtotal = amount_due for legacy invoices
                inv.subtotal = inv.amount_due
                inv.save(update_fields=['subtotal'])
            except FeeStructure.DoesNotExist:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('finance', '0001_initial'),
    ]

    operations = [
        # Step 1: Add new fields (nullable/blank first)
        migrations.AddField(
            model_name='invoice',
            name='invoice_number',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='invoice',
            name='class_group',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoices',
                to='academics.classgroup',
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='subtotal',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Sum of all line items before discount', max_digits=10),
        ),
        migrations.AddField(
            model_name='invoice',
            name='discount_description',
            field=models.CharField(blank=True, default='', max_length=200, help_text='e.g., Sibling Discount, Merit Scholarship'),
        ),
        migrations.AddField(
            model_name='invoice',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='amount_due',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Subtotal minus discount', max_digits=10),
        ),

        # Step 2: Create InvoiceLineItem model
        migrations.CreateModel(
            name='InvoiceLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(help_text='Fee description', max_length=200)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fee_structure', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='finance.feestructure',
                )),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='line_items',
                    to='finance.invoice',
                )),
            ],
        ),

        # Step 3: Migrate existing data
        migrations.RunPython(migrate_fee_structure_to_line_items, migrations.RunPython.noop),

        # Step 4: Populate invoice numbers for existing records
        migrations.RunPython(populate_invoice_numbers, migrations.RunPython.noop),

        # Step 5: Now make invoice_number unique
        migrations.AlterField(
            model_name='invoice',
            name='invoice_number',
            field=models.CharField(blank=True, max_length=30),
        ),

        # Step 6: Remove old fee_structure FK
        migrations.RemoveField(
            model_name='invoice',
            name='fee_structure',
        ),
    ]
