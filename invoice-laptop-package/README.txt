STACKSTONE INVOICE GENERATOR — WINDOWS PACKAGE
==============================================

This is a self-contained offline invoice-preparation tool. It does not need
Python, Node, a server, credentials, or an internet connection.
The invoice preview follows the supplied Stackstone PDF using the supplied
Stackstone logo and charcoal/gold visual system.

QUICK START
-----------
1. Save this ZIP somewhere convenient.
2. On a Windows laptop, extract the ZIP to a normal folder.
3. Double-click invoice-generator.html.
4. Enter the client and invoice details. Your seller and payment details are
   prefilled and can also be edited.
5. Click "Print to PDF", choose "Microsoft Print to PDF", and save the PDF.

Choose the correct client folder and filename in the Windows save dialog. The
generator does not assume a particular client, folder, or document system.

The ZIP also includes stackstone-logo.png, the cropped copy of the supplied
Stackstone horizontal logo used by the generator and invoice preview.

For a new invoice, click "New invoice". Enter a new, unique invoice reference.
Use "Save draft JSON" to keep a portable editable backup and "Load draft JSON"
to reopen one later. The app opens as a blank, client-agnostic template.

SAFETY NOTES
------------
- "Print to PDF" creates a local PDF only; choose the final storage location
  yourself in the Windows print dialog.
- This package never sends an email.
- This package never updates the invoice tracker.
- This package never marks an invoice as sent.
- Check the invoice number, client, dates, amount, bank details, and tax/VAT
  treatment before uploading or sending the resulting PDF.
- The generator shows a warning when a tax/VAT rate is entered. Confirm the
  legal treatment separately; do not rely on this tool as tax advice.