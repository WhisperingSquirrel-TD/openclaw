#!/usr/bin/env python3
"""Generate Stackstone Consulting invoice PDF from JSON specification."""

import json
import sys
from pathlib import Path

def generate_html(invoice_data):
    """Generate HTML invoice matching Stackstone template format."""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Invoice {invoice_data['reference']}</title>
    <style>
        body {{
            font-family: 'Calibri', 'Arial', sans-serif;
            margin: 40px;
            font-size: 11pt;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 30px;
        }}
        .header-left {{
            flex: 1;
        }}
        .header-right {{
            text-align: right;
        }}
        .logo {{
            font-size: 16pt;
            font-weight: bold;
            color: #1a1a1a;
            margin-bottom: 5px;
        }}
        .logo-subtext {{
            font-size: 9pt;
            letter-spacing: 3px;
            color: #666;
        }}
        .company-info {{
            font-size: 9pt;
            line-height: 1.4;
            margin-top: 10px;
        }}
        .invoice-title {{
            font-size: 24pt;
            font-weight: bold;
            margin-bottom: 20px;
        }}
        .invoice-details {{
            display: flex;
            gap: 40px;
            margin-bottom: 30px;
        }}
        .invoice-details table {{
            border-collapse: collapse;
        }}
        .invoice-details td {{
            padding: 4px 8px;
            font-size: 10pt;
        }}
        .invoice-details .label {{
            font-weight: bold;
        }}
        .bill-to {{
            margin-bottom: 30px;
        }}
        .bill-to-label {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .items-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        .items-table th {{
            background-color: #f0f0f0;
            padding: 8px;
            text-align: left;
            font-weight: bold;
            border: 1px solid #ccc;
        }}
        .items-table td {{
            padding: 8px;
            border: 1px solid #ccc;
        }}
        .items-table .right {{
            text-align: right;
        }}
        .items-table .center {{
            text-align: center;
        }}
        .total {{
            text-align: right;
            font-size: 14pt;
            font-weight: bold;
            margin: 20px 0;
        }}
        .payment-section {{
            margin-top: 40px;
        }}
        .payment-title {{
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .payment-table {{
            border-collapse: collapse;
        }}
        .payment-table td {{
            padding: 4px 12px 4px 0;
        }}
        .payment-table .label {{
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <div style="font-size: 10pt; margin-bottom: 5px;"><strong>Trading Name</strong></div>
            <div style="font-size: 11pt; margin-bottom: 20px;">{invoice_data['trading_name']}</div>
            <div class="logo">STACKSTONE</div>
            <div class="logo-subtext">CONSULTING</div>
        </div>
        <div class="header-right">
            <div style="font-size: 9pt; margin-bottom: 5px;"><strong>Registered Business Name</strong></div>
            <div class="company-info">
                {invoice_data['registered_name']}<br>
                {invoice_data['company_address']}<br>
                <br>
                {invoice_data['company_email']}<br>
                {invoice_data['company_phone']}<br>
                Company no. - {invoice_data['company_number']}
            </div>
        </div>
    </div>

    <div class="invoice-title">INVOICE</div>

    <div class="invoice-details">
        <table>
            <tr>
                <td class="label">Reference</td>
                <td>{invoice_data['reference']}</td>
            </tr>
            <tr>
                <td class="label">Amount due</td>
                <td>£{invoice_data['total']:,.2f}</td>
            </tr>
            <tr>
                <td class="label">Due date</td>
                <td>{invoice_data['due_date']}</td>
            </tr>
            <tr>
                <td class="label">Issue date</td>
                <td>{invoice_data['issue_date']}</td>
            </tr>
        </table>
        <div>
            <div class="bill-to-label">To</div>
            <div style="font-size: 10pt; line-height: 1.4;">
                {invoice_data['client_name']}<br>
                {invoice_data['client_address'].replace(', ', '<br>')}<br>
                <br>
                {invoice_data['client_email']}<br>
                {invoice_data.get('client_phone', '')}
            </div>
        </div>
    </div>

    <table class="items-table">
        <thead>
            <tr>
                <th>Description</th>
                <th class="center">Qty</th>
                <th class="right">Unit cost</th>
                <th class="right">Amount</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for item in invoice_data['line_items']:
        html += f"""            <tr>
                <td>{item['description']}</td>
                <td class="center">{item['quantity']}</td>
                <td class="right">£{item['unit_cost']:,.2f}</td>
                <td class="right">£{item['amount']:,.2f}</td>
            </tr>
"""
    
    html += f"""        </tbody>
    </table>

    <div class="total">Total<br>£{invoice_data['total']:,.2f}</div>

    <div class="payment-section">
        <div class="payment-title">PAYMENT METHODS</div>
        <table class="payment-table">
            <tr>
                <td class="label">Account name</td>
                <td>{invoice_data['bank_account_name']}</td>
            </tr>
            <tr>
                <td class="label">Account number</td>
                <td>{invoice_data['bank_account_number']}</td>
            </tr>
            <tr>
                <td class="label">Sort code</td>
                <td>{invoice_data['bank_sort_code']}</td>
            </tr>
        </table>
    </div>
</body>
</html>"""
    
    return html


def preflight_check(invoice_data):
    """Verify all required fields are present."""
    required = ['registered_name', 'trading_name', 'reference', 'company_number']
    missing = [f for f in required if not invoice_data.get(f)]
    
    if missing:
        print(f"❌ PREFLIGHT FAILED - Missing fields: {', '.join(missing)}")
        return False
    
    print("✓ Preflight check passed:")
    print(f"  - Registered name: {invoice_data['registered_name']}")
    print(f"  - Trading name: {invoice_data['trading_name']}")
    print(f"  - Reference: {invoice_data['reference']}")
    print(f"  - Company number: {invoice_data['company_number']}")
    return True


def main():
    if len(sys.argv) != 2:
        print("Usage: generate-invoice.py <invoice-data.json>")
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"Error: {json_file} not found")
        sys.exit(1)
    
    with open(json_file) as f:
        invoice_data = json.load(f)
    
    # Preflight check
    if not preflight_check(invoice_data):
        sys.exit(1)
    
    # Generate HTML
    html = generate_html(invoice_data)
    
    # Write HTML file
    html_file = json_file.with_suffix('.html')
    with open(html_file, 'w') as f:
        f.write(html)
    
    print(f"\n✓ Generated HTML: {html_file}")
    print(f"  Reference: {invoice_data['reference']}")
    print(f"  Amount: £{invoice_data['total']:,.2f}")
    
    # Try to generate PDF using chromium if available
    import subprocess
    try:
        pdf_file = json_file.with_suffix('.pdf')
        result = subprocess.run(
            ['chromium', '--headless', '--disable-gpu', 
             f'--print-to-pdf={pdf_file}', '--no-pdf-header-footer', 
             str(html_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"✓ Generated PDF: {pdf_file}")
        else:
            print(f"⚠ PDF generation failed: {result.stderr}")
            print("  HTML file is ready for manual conversion")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"⚠ Could not generate PDF: {e}")
        print("  HTML file is ready for manual conversion")


if __name__ == '__main__':
    main()
