from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.acroform import AcroForm
from reportlab.lib.enums import TA_CENTER

OUT = 'Tom-Dean-LGPS-Form-3-recreated-editable.pdf'
W, H = letter
c = canvas.Canvas(OUT, pagesize=letter, pageCompression=1)
c.setTitle('Form 3 – Deferred refund member | Payment of Cash Transfer Sum')
c.setAuthor('Tom Dean')

# Visual constants
left, right = 54, W - 54
green, purple, blue = HexColor('#4c8b2b'), HexColor('#64509a'), HexColor('#1f5fae')
font, bold = 'Helvetica', 'Helvetica-Bold'

# Simple vector Oxfordshire Pension Fund mark (recreated, not a raster background)
c.setStrokeColor(green); c.setLineWidth(1.8)
c.line(73, H-56, 73, H-31); c.line(73, H-44, 64, H-34); c.line(73, H-39, 82, H-30)
c.setFillColor(purple)
for x,y,r in [(63,H-32,3.8),(82,H-28,4.2),(73,H-52,3.4)]:
    c.circle(x,y,r,fill=1,stroke=0)
c.setFillColor(green); c.setFont(bold, 9.8); c.drawString(91,H-35,'Oxfordshire')
c.drawString(91,H-47,'Pension Fund')
c.setFont(font,5.5); c.drawString(91,H-55,'www.oxfordshire.gov.uk/pensions')

# Header
c.setFillColor(black)
c.setFont(font, 10.6)
c.drawCentredString(W/2+18,H-34,'Form 3 – Deferred refund member')
c.setFont(bold, 10.6)
c.drawCentredString(W/2+18,H-47,'Payment of Cash Transfer Sum to Personal Pension Scheme')
c.setFont(bold, 12.4)
c.drawCentredString(W/2,H-83,'DECLARATION AND ELECTION FOR PAYMENT OF A CASH TRANSFER SUM')
c.setFont(bold, 10)
c.drawString(left,H-108,'I declare that:')

# text utilities
def draw_wrapped(text, x, y, max_width, size=8.7, leading=11.0, bullet=False, strike_phrase=None):
    words = text.split()
    lines, cur = [], ''
    for word in words:
        test = word if not cur else cur + ' ' + word
        if stringWidth(test, font, size) <= max_width:
            cur = test
        else:
            lines.append(cur); cur = word
    if cur: lines.append(cur)
    for i,line in enumerate(lines):
        if bullet and i == 0:
            c.setFont(font, size); c.drawString(x-12,y,'•')
        c.setFont(font,size); c.drawString(x,y,line)
        if strike_phrase and strike_phrase in line:
            start = x + stringWidth(line[:line.index(strike_phrase)], font, size)
            end = start + stringWidth(strike_phrase, font, size)
            c.setStrokeColor(black); c.setLineWidth(0.65)
            c.line(start, y + size * 0.32, end, y + size * 0.32)
            strike_phrase = None
        y -= leading
    return y

y = H-128
body_x, body_w = left+17, right-(left+17)
bullets = [
'I have received details of the refund of contributions (including any deduction for tax and contributions equivalent premium, where appropriate) I would be entitled to under the Local Government Pension Scheme (LGPS) in the Oxfordshire Pension Fund and details of the cash transfer sum (CETV) I may transfer to another scheme',
'I have received a statement from the scheme(s) to which I wish the cash transfer sum to be paid showing the benefits the transfer payment would buy for me in that scheme or schemes',
'If I have not quoted a National Insurance number on this form this is because I do not qualify for one',
]
for b in bullets:
    y = draw_wrapped(b,body_x,y,body_w,bullet=True); y -= 4

# Choice bullets: rendered as real selectable text, preserving the supplied form's inline style.
def choice_bullet(text, y, strike_phrase):
    return draw_wrapped(text, body_x, y, body_w, 8.7, 11.0, bullet=True, strike_phrase=strike_phrase) - 4

# Match the completed source: delete the inapplicable option in each declaration.
y = choice_bullet('I am / am not [please delete as appropriate] already in receipt of a pension from the LGPS (other than (i) a survivor’s pension or (ii) a pension derived from a Pension Credit granted to me following a divorce or dissolution of a civil partnership)', y, 'am')
y = choice_bullet('In addition to the rights I elect to transfer to the scheme named on this form, I hold / do not hold [please delete as appropriate] any other LGPS pension rights that are not in payment (other than a pension derived from a Pension Credit granted to me following a divorce or dissolution of a civil partnership)', y, 'do not hold')

# Short separator line
c.setStrokeColor(black)
y -= 1
c.setLineWidth(.4); c.line(body_x,y,body_x+130,y); y -= 17
y = choice_bullet('I am / am not [please delete as appropriate] still an active member of the LGPS (i.e. still paying pension contributions to the LGPS)', y, 'am')

# Declaration and signature section
c.setFont(bold,9.4)
declaration = 'To the best of my knowledge and belief, I declare the information given on all the pages of this form is correct and complete.'
# declaration wrap if needed
for line in [declaration]:
    c.drawString(left,y-3,line)
y -= 35

# signature image + editable date field
sig_path = 'reference/signatures/2026-07-13-tom-signature.jpg'
try:
    c.drawImage(sig_path,left+40,y-8,width=155,height=29,mask='auto',preserveAspectRatio=True,anchor='sw')
except Exception:
    pass
c.setFont(font,9)
c.drawString(left,y-13,'Signed ')
c.setDash(1.2,1.5); c.line(left+34,y-10,left+222,y-10); c.setDash()
c.drawString(left+252,y-13,'Date')
c.setDash(1.2,1.5); c.line(left+279,y-10,left+372,y-10); c.setDash()
c.setFillColor(blue); c.setFont(font,9); c.drawString(left+280,y-13,'23/07/2026'); c.setFillColor(black)
y -= 40

small = ('A wet signature is required (physical marking with a pen) and must be signed by the member only. If a digital signature is used or the form appears to be signed by anyone other than by the member, the form will be returned to the member for completion with a wet signature. This may result in a delay in completing the transfer.')
draw_wrapped(small,left,y,right-left,size=6.6,leading=8.0)
c.setFont(font,8); c.drawCentredString(W/2,22,'1')
c.save()
print(OUT)
