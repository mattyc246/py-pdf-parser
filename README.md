# CSV Resume Parser

This script reads a CSV of candidate resume URLs, downloads each PDF, extracts text, and appends screening columns for hospitality, retail, role matches, and relevant experience years.

## Run

```bash
python3 main.py
```

Process only the first 10 rows:

```bash
python3 main.py --limit 10
```

Use a custom input or output path:

```bash
python3 main.py --input /path/to/source.csv --output /path/to/enriched.csv
```

## Output Columns

The script preserves the original CSV columns and appends:

- `has_fnb_experience`
- `has_retail_experience`
- `relevant_experience_years`
- `has_waiter_or_service_role`
- `has_baker_or_cake_decorator_role`
- `has_retail_supervisor_role`
- `has_sales_assistant_role`

Rows without a resume URL, failed downloads, unreadable PDFs, or empty resume text receive `-` in all appended columns.
