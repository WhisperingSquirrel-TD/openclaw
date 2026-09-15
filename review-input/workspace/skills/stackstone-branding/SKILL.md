---
name: stackstone-branding
description: Apply Stackstone Consulting house style—colours, typography, layout, headers, footers, and table patterns—to client-facing deliverables.
---

# Stackstone Consulting — Brand Reference

Use this skill as the single source of truth for Stackstone Consulting visual identity across client-facing deliverables.
The approved Croyde Medical AI Opportunity Assessment (March 2026) is the reference document for this output style.

## Core rules
- Use **Arial** throughout. No other fonts.
- Use the Stackstone palette exactly.
- Use **AMBER** for brand accents, not body text.
- Use **CHARCOAL** for title authority elements, not body text.
- Use **SLATE** for body copy, metadata, footer text, and table body text.
- Use **LIGHT_BG** sparingly for warm alternating rows / callouts.
- Use **AMBER_LIGHT** only for highlights, recommendations, key findings, and standout cells.

## Brand constants
```javascript
const CHARCOAL   = "2D2D2D"; // Titles, H1/H3, table header fill
const AMBER      = "D97706"; // Brand name, H2, dividers, contact line, header text
const SLATE      = "4A5568"; // Body text, subtitles, footer, metadata, table body
const LIGHT_BG   = "F7F5F2"; // Alternating rows, callout backgrounds
const WHITE      = "FFFFFF"; // Page background, table header text
const BORDER_COL = "CBD5E0"; // Table borders
const AMBER_LIGHT = "FEF3C7"; // Highlight/recommendation cells
```

## Typography
| Element | Half-pts | Pts | Weight | Colour | Notes |
|---|---:|---:|---|---|---|
| Brand name (cover) | 22 | 11 | Bold | AMBER | characterSpacing: 200 |
| Document title (cover) | 56 | 28 | Bold | CHARCOAL | Main title |
| Document subtitle (cover) | 36 | 18 | Regular | SLATE | Client name / document type |
| Metadata (cover) | 22 | 11 | Regular | SLATE | Prepared by / date / classification |
| Contact line (cover) | 18 | 9 | Regular | AMBER | Email / website / phone |
| H1 | 36 | 18 | Bold | CHARCOAL | outlineLevel 0 |
| H2 | 28 | 14 | Bold | AMBER | outlineLevel 1 |
| H3 | 24 | 12 | Bold | CHARCOAL | outlineLevel 2 |
| Body text | 22 | 11 | Regular | SLATE | spacing after 160, line 300 |
| Table header | 20 | 10 | Bold | WHITE | on CHARCOAL fill |
| Table body | 20 | 10 | Regular | SLATE | |
| Bullets / numbered | 22 | 11 | Regular | SLATE | left 720, hanging 360 |
| Running header | 16 | 8 | Italic | AMBER | right-aligned |
| Running footer | 16 | 8 | Regular | SLATE | centred |
| Evidence / source notes | 18 | 9 | Italic | SLATE | attribution blocks |

## Page setup
- Paper size: **A4** (`11906 x 16838 DXA`)
- Margins: **1 inch all sides** (`1440 DXA`)
- Content width: **9026 DXA**

## Cover page layout
1. Large spacer (~2400)
2. `STACKSTONE CONSULTING` — AMBER, 11pt, bold, characterSpacing 200, left-aligned
3. Amber divider line
4. Document title — CHARCOAL, 28pt, bold
5. Subtitle / client name — SLATE, 18pt
6. Spacer (~600)
7. Amber divider line
8. Prepared by / Date / Classification — SLATE, 11pt
9. Spacer (~1200)
10. Contact line — AMBER, 9pt:
   `tom@stackstoneconsulting.co.uk | stackstoneconsulting.co.uk | 07894 241 276`

## Cover page implementation
```javascript
new Paragraph({
  alignment: AlignmentType.LEFT,
  spacing: { after: 80 },
  children: [new TextRun({
    text: "STACKSTONE CONSULTING",
    size: 22,
    font: "Arial",
    color: AMBER,
    bold: true,
    characterSpacing: 200,
  })],
});

new Paragraph({
  spacing: { before: 200, after: 200 },
  border: {
    bottom: { style: BorderStyle.SINGLE, size: 4, color: AMBER, space: 8 },
  },
  children: [],
});
```

## Running header
```javascript
headers: {
  default: new Header({
    children: [new Paragraph({
      alignment: AlignmentType.RIGHT,
      children: [new TextRun({
        text: "[Client Name] — [Document Title]",
        size: 16,
        font: "Arial",
        color: AMBER,
        italics: true,
      })],
    })],
  }),
}
```

## Running footer
```javascript
footers: {
  default: new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({
          text: "Stackstone Consulting | Confidential | Page ",
          size: 16,
          font: "Arial",
          color: SLATE,
        }),
        new TextRun({
          children: [PageNumber.CURRENT],
          size: 16,
          font: "Arial",
          color: SLATE,
        }),
      ],
    })],
  }),
}
```

## Table styling
- Always use `WidthType.DXA`, never percentages.
- Set widths on both the table columns and each cell.
- Header row: **CHARCOAL fill**, **WHITE bold text**.
- Body rows: **WHITE** or alternating **LIGHT_BG**.
- Highlight cells: **AMBER_LIGHT**.
- Cell padding: `{ top: 80, bottom: 80, left: 120, right: 120 }`
- Border colour: `BORDER_COL`
- Use `ShadingType.CLEAR`, never `SOLID`.

```javascript
const border = { style: BorderStyle.SINGLE, size: 1, color: BORDER_COL };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: CHARCOAL, type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({
      children: [new TextRun({ text, bold: true, size: 20, font: "Arial", color: WHITE })],
    })],
  });
}

function dataCell(text, width, opts = {}) {
  const fill = opts.highlight ? AMBER_LIGHT : opts.shade ? LIGHT_BG : WHITE;
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({ text, size: 20, font: "Arial", color: SLATE, ...opts })],
    })],
  });
}
```

## End-of-document pattern
```javascript
sectionDivider();

new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 80 },
  children: [new TextRun({
    text: "End of Report",
    size: 20,
    font: "Arial",
    color: SLATE,
    italics: true,
  })],
});

new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({
    text: "Stackstone Consulting — tom@stackstoneconsulting.co.uk — 07894 241 276",
    size: 18,
    font: "Arial",
    color: AMBER,
  })],
});
```

## Common helpers
```javascript
function body(text, opts = {}) {
  const runs = [];
  if (typeof text === "string") {
    runs.push(new TextRun({ text, size: 22, font: "Arial", color: SLATE, ...opts }));
  } else {
    text.forEach(r => runs.push(new TextRun({ size: 22, font: "Arial", color: SLATE, ...r })));
  }
  return new Paragraph({ spacing: { after: 160, line: 300 }, children: runs });
}

function spacer(pts = 120) {
  return new Paragraph({ spacing: { after: pts }, children: [] });
}

function sectionDivider() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 4, color: AMBER, space: 8 },
    },
    children: [],
  });
}
```

## Default docx-js styles
```javascript
styles: {
  default: {
    document: {
      run: { font: "Arial", size: 22, color: SLATE },
    },
  },
  paragraphStyles: [
    {
      id: "Heading1",
      name: "Heading 1",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: { size: 36, bold: true, font: "Arial", color: CHARCOAL },
      paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
    },
    {
      id: "Heading2",
      name: "Heading 2",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: { size: 28, bold: true, font: "Arial", color: AMBER },
      paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 },
    },
    {
      id: "Heading3",
      name: "Heading 3",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: { size: 24, bold: true, font: "Arial", color: CHARCOAL },
      paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
    },
  ],
}
```

## Use with stackstone-report
- Use this skill whenever the report-writing flow creates a client-facing document.
- Prefer this as the brand source of truth instead of ad hoc README snippets.
- If a report conflicts with this file, this file wins unless Tom explicitly overrides it.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
