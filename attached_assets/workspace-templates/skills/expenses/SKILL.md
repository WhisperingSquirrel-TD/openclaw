# SKILL: Expenses — Log and Review

## When to use
- When Tom mentions an expense to log
- When asked "what have I spent this month"
- End of month expense review

## Where expenses are stored
`~/.openclaw/workspace/reference/EXPENSES.md`
Create this file if it does not exist.

## Log format
```
| Date | Description | Amount | Category | Notes |
|---|---|---|---|---|
| YYYY-MM-DD | Item description | £X.XX | Category | Optional note |
```

## Categories
- Travel (mileage, train, parking, flights)
- Meals (client entertainment, subsistence)
- Software / subscriptions
- Equipment / office
- Professional (training, memberships, books)
- Other

## Process — logging an expense
1. Ask for: date, description, amount, category (infer if obvious)
2. Append to EXPENSES.md in the correct format
3. Confirm: "Logged — £X for [description] on [date]"

## Process — monthly review
1. Read EXPENSES.md
2. Group by category
3. Sum each category and total
4. Highlight anything unusual or large
5. Ask if Tom wants to export (produces a formatted summary)

## Mileage
HMRC rate: 45p/mile (first 10,000 miles), 25p/mile thereafter.
Log as: mileage in miles, auto-calculate amount.
