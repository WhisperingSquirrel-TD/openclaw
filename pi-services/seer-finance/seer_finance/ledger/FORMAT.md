# Transaction data format for OpenClaw

This is the contract between OpenClaw (which reads SEER's expenses and invoices)
and the ledger (which classifies them into Corporation Tax figures). OpenClaw
produces a JSON array of transaction objects in exactly this shape. The loader
validates strictly and rejects anything malformed, so follow this precisely.

## Top level

A JSON array (`[ ... ]`) of transaction objects. Nothing else.

## Transaction object

| Field           | Required | Type    | Notes                                                              |
| --------------- | -------- | ------- | ------------------------------------------------------------------ |
| `txn_id`        | yes      | string  | Unique per transaction. Duplicates are rejected.                   |
| `date`          | yes      | string  | ISO `YYYY-MM-DD`. Must be a real calendar date.                    |
| `direction`     | yes      | string  | `income` or `expense`.                                             |
| `amount_pence`  | yes      | integer | Positive whole number of **pence**. See below.                     |
| `description`   | yes      | string  | What it was.                                                       |
| `counterparty`  | yes      | string  | Who it was with.                                                   |
| `category`      | yes      | string  | One of the controlled categories below.                            |
| `pre_trading`   | no       | boolean | `true` if incurred before the trading-start date. Default `false`. |
| `tax_treatment` | no       | string  | Override the category default. Usually omit.                       |
| `source_ref`    | no       | string  | Reference/link to the invoice or receipt.                          |

Unknown fields are rejected (guards against typos silently dropping data).

## Money: always integer pence

`amount_pence` MUST be a whole number of pence as an integer.

- £1,800.00 -> `180000`
- £14.99 -> `1499`
- Do NOT send pounds (`1800`), floats (`1800.00`), or strings (`"1800"`).
  All are rejected. This keeps money arithmetic exact.

Always send a positive amount; use `direction` to say whether it is money in or
out. Never send a negative amount.

## Categories

Pick the closest category. The ledger derives the correct Corporation Tax
treatment from it automatically, so you do not need to know the tax rules — just
categorise plausibly. Use `other` only when nothing fits; it forces a manual
review before filing.

Income: `sales`

Allowable expenses: `software`, `subscriptions`, `professional_fees`,
`insurance`, `travel`, `training`, `office_costs`, `phone_internet`,
`bank_charges`, `marketing`, `stock_consumables`, `staff_costs`, `use_of_home`,
`pension`

Usually disallowable: `client_entertainment`, `gifts`, `fines_penalties`,
`depreciation`

Capital (equipment with lasting value): `equipment`

Non-trading / drawings: `dividend`, `directors_loan`, `corporation_tax_payment`,
`vat_payment`

Catch-all: `other`

## Overriding the tax treatment

Omit `tax_treatment` in almost all cases — let the category decide. Set it only
for genuine edge cases, e.g. a small item of equipment expensed rather than
capitalised: `"category": "equipment", "tax_treatment": "allowable"`.

Valid values: `allowable`, `disallowable`, `capital`, `income`, `non_trading`.

## Minimal example

```json
[
  {
    "txn_id": "inv-001",
    "date": "2026-02-10",
    "direction": "income",
    "amount_pence": 180000,
    "description": "Consultancy - discovery engagement",
    "counterparty": "Example Client Ltd",
    "category": "sales",
    "source_ref": "INV-001"
  },
  {
    "txn_id": "exp-001",
    "date": "2026-02-01",
    "direction": "expense",
    "amount_pence": 1499,
    "description": "Accounting software (monthly)",
    "counterparty": "SoftwareCo",
    "category": "software",
    "source_ref": "receipt-11"
  }
]
```
