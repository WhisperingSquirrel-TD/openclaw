STACKSTONE INVOICE GENERATOR — WINDOWS PACKAGE
==============================================

This is a self-contained offline invoice-preparation tool. It does not need
Python, Node, a server, credentials, or an internet connection.

QUICK START
-----------
1. Save this ZIP in SharePoint if you want it backed up or shared.
2. On a Windows laptop, extract the ZIP to a normal folder.
3. Double-click invoice-generator.html.
4. Review or edit the prefilled invoice.
5. Click "Print / Save PDF", choose "Microsoft Print to PDF", and save the PDF.
6. Upload the PDF manually to the displayed SharePoint path.

The starting data is the Croyde Medical invoice:
  Reference: INV-082
  Issue date: 03/09/2026
  Due date: 04/09/2026
  Total: £3,500.00

For a new invoice, click "New invoice". Enter a new, unique invoice reference.
The seller and payment details remain prefilled, while client and invoice fields
are cleared. Use "Save draft JSON" to keep a portable editable backup and
"Load draft JSON" to reopen one later.

SHAREPOINT
----------
The tool intentionally does not contain Microsoft credentials and cannot upload
directly to SharePoint. It displays the correct destination path for manual
upload. The current invoice destination is:

  /Accounts/Croyde Medical/Finance/03/09/2026 - Invoice - INV-082.pdf

If the SharePoint library requires a different date naming convention, edit the
displayed invoice date before printing or rename the PDF during upload.

SAFETY NOTES
------------
- "Print / Save PDF" creates a local PDF only.
- This package never sends an email.
- This package never updates the invoice tracker.
- This package never marks an invoice as sent.
- Check the invoice number, client, dates, amount, bank details, and tax/VAT
  treatment before uploading or sending the resulting PDF.
- The generator shows a warning when a tax/VAT rate is entered. Confirm the
  legal treatment separately; do not rely on this tool as tax advice.