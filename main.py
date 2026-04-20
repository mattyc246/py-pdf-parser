from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pymupdf
import requests


APPENDED_COLUMNS = [
    "has_fnb_experience",
    "has_retail_experience",
    "relevant_experience_years",
    "has_waiter_or_service_role",
    "has_baker_or_cake_decorator_role",
    "has_retail_supervisor_role",
    "has_sales_assistant_role",
]

MISSING_VALUE = "-"

MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

DATE_TOKEN = (
    r"(?:"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+\d{4}"
    r"|"
    r"\d{1,2}[/-]\d{4}"
    r"|"
    r"\d{4}"
    r")"
)
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{DATE_TOKEN})\s*(?:-|–|—|to|until|till)\s*(?P<end>{DATE_TOKEN}|present|current|now)",
    re.IGNORECASE,
)

FNB_TERMS = [
    "fnb",
    "food beverage",
    "food and beverage",
    "restaurant",
    "cafe",
    "café",
    "coffee",
    "bar",
    "dining",
    "bistro",
    "hospitality",
    "front of house",
    "back of house",
    "kitchen",
    "bakery",
    "pastry",
    "host",
    "hostess",
    "guest relations",
    "banquet",
]

RETAIL_TERMS = [
    "retail",
    "store",
    "shop",
    "outlet",
    "boutique",
    "showroom",
    "sales floor",
    "cashier",
    "merchandiser",
    "visual merchandising",
    "point of sale",
]

WAITER_TERMS = [
    "waiter",
    "waitress",
    "server",
    "service crew",
    "guest experience",
    "guest service",
    "crew member",
    "food server",
    "host",
    "hostess",
    "floor staff",
]

BAKER_TERMS = [
    "baker",
    "bakery assistant",
    "cake decorator",
    "cake deco",
    "pastry chef",
    "pastry cook",
    "pastry assistant",
    "bread maker",
]

SUPERVISOR_TERMS = [
    "supervisor",
    "senior supervisor",
    "store supervisor",
    "shop supervisor",
    "retail supervisor",
    "floor supervisor",
    "outlet supervisor",
]

SALES_ASSISTANT_TERMS = [
    "sales assistant",
    "shop assistant",
    "store assistant",
    "retail assistant",
    "sales associate",
    "store associate",
    "shop assisitant",
    "store assisitant",
    "sales assisitant",
    "sales advisor",
    "retail sales assistant",
]


@dataclass(frozen=True)
class ExperienceSegment:
    start_month_index: int
    end_month_index: int
    context: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a candidate CSV, parse resume PDFs, and append screening columns."
    )
    parser.add_argument(
        "--input",
        default="poll_users_with_resume_url.csv",
        help="Path to the source CSV file.",
    )
    parser.add_argument(
        "--output",
        default="poll_users_with_resume_url_enriched.csv",
        help="Path to the enriched output CSV file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N data rows.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s/-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compile_term_patterns(terms: Iterable[str]) -> list[re.Pattern[str]]:
    patterns = []
    for term in terms:
        normalized_term = normalize_text(term)
        parts = [re.escape(part) for part in normalized_term.split()]
        if not parts:
            continue
        patterns.append(re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE))
    return patterns


FNB_PATTERNS = compile_term_patterns(FNB_TERMS)
RETAIL_PATTERNS = compile_term_patterns(RETAIL_TERMS)
WAITER_PATTERNS = compile_term_patterns(WAITER_TERMS)
BAKER_PATTERNS = compile_term_patterns(BAKER_TERMS)
SUPERVISOR_PATTERNS = compile_term_patterns(SUPERVISOR_TERMS)
SALES_ASSISTANT_PATTERNS = compile_term_patterns(SALES_ASSISTANT_TERMS)


def contains_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def read_csv_rows(input_path: Path, limit: int | None) -> tuple[list[str], list[dict[str, str]]]:
    with input_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = list(reader.fieldnames or [])
        rows = []
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            rows.append(dict(row))
    return fieldnames, rows


def download_resume(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        return "\n".join(page.get_text("text") for page in document)


def parse_month_index(token: str, is_end: bool) -> int | None:
    token = token.strip().lower().replace(".", "")
    if token in {"present", "current", "now"}:
        now = datetime.now()
        return now.year * 12 + (now.month - 1)

    numeric_match = re.fullmatch(r"(?P<month>\d{1,2})[/-](?P<year>\d{4})", token)
    if numeric_match:
        month = int(numeric_match.group("month"))
        year = int(numeric_match.group("year"))
        if 1 <= month <= 12:
            return year * 12 + (month - 1)
        return None

    month_match = re.fullmatch(r"(?P<month>[a-z]+)\s+(?P<year>\d{4})", token)
    if month_match:
        month_name = month_match.group("month")
        month_number = MONTH_ALIASES.get(month_name)
        if month_number is None:
            return None
        year = int(month_match.group("year"))
        return year * 12 + (month_number - 1)

    if re.fullmatch(r"\d{4}", token):
        year = int(token)
        month = 12 if is_end else 1
        return year * 12 + (month - 1)

    return None


def extract_experience_segments(text: str) -> list[ExperienceSegment]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    segments: list[ExperienceSegment] = []
    seen: set[tuple[int, int, str]] = set()

    for index in range(len(lines)):
        window_lines = lines[index : index + 3]
        if not window_lines:
            continue

        window_text = " ".join(window_lines)
        for match in DATE_RANGE_RE.finditer(window_text):
            start_index = parse_month_index(match.group("start"), is_end=False)
            end_index = parse_month_index(match.group("end"), is_end=True)
            if start_index is None or end_index is None or end_index < start_index:
                continue

            context_start = max(0, index - 2)
            context_end = min(len(lines), index + 4)
            context = normalize_text(" ".join(lines[context_start:context_end]))
            key = (start_index, end_index, context)
            if key in seen:
                continue
            seen.add(key)
            segments.append(
                ExperienceSegment(
                    start_month_index=start_index,
                    end_month_index=end_index,
                    context=context,
                )
            )

    return segments


def merge_month_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    ordered = sorted(ranges)
    merged = [ordered[0]]

    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def months_to_rounded_years(total_months: int) -> int:
    if total_months <= 0:
        return 0
    return math.ceil(total_months / 12)


def empty_analysis() -> dict[str, str]:
    return {column: MISSING_VALUE for column in APPENDED_COLUMNS}


def analyze_resume_text(text: str) -> dict[str, str]:
    normalized_text = normalize_text(text)
    segments = extract_experience_segments(text)

    has_fnb_experience = contains_any(normalized_text, FNB_PATTERNS)
    has_retail_experience = contains_any(normalized_text, RETAIL_PATTERNS)
    has_waiter_or_service_role = contains_any(normalized_text, WAITER_PATTERNS)
    has_baker_or_cake_decorator_role = contains_any(normalized_text, BAKER_PATTERNS)
    has_sales_assistant_role = contains_any(normalized_text, SALES_ASSISTANT_PATTERNS)
    has_retail_supervisor_role = False

    relevant_ranges: list[tuple[int, int]] = []

    for segment in segments:
        is_fnb_segment = contains_any(segment.context, FNB_PATTERNS)
        is_retail_segment = contains_any(segment.context, RETAIL_PATTERNS)

        if is_fnb_segment:
            has_fnb_experience = True
        if is_retail_segment:
            has_retail_experience = True
        if contains_any(segment.context, WAITER_PATTERNS):
            has_waiter_or_service_role = True
        if contains_any(segment.context, BAKER_PATTERNS):
            has_baker_or_cake_decorator_role = True
        if contains_any(segment.context, SALES_ASSISTANT_PATTERNS):
            has_sales_assistant_role = True
        if is_retail_segment and contains_any(segment.context, SUPERVISOR_PATTERNS):
            has_retail_supervisor_role = True
        if is_fnb_segment or is_retail_segment:
            relevant_ranges.append((segment.start_month_index, segment.end_month_index))

    if not has_retail_supervisor_role:
        has_retail_supervisor_role = contains_any(normalized_text, SUPERVISOR_PATTERNS) and has_retail_experience

    merged_ranges = merge_month_ranges(relevant_ranges)
    total_relevant_months = sum((end - start) + 1 for start, end in merged_ranges)
    relevant_experience_years = months_to_rounded_years(total_relevant_months)

    return {
        "has_fnb_experience": "TRUE" if has_fnb_experience else "FALSE",
        "has_retail_experience": "TRUE" if has_retail_experience else "FALSE",
        "relevant_experience_years": str(relevant_experience_years),
        "has_waiter_or_service_role": "TRUE" if has_waiter_or_service_role else "FALSE",
        "has_baker_or_cake_decorator_role": "TRUE" if has_baker_or_cake_decorator_role else "FALSE",
        "has_retail_supervisor_role": "TRUE" if has_retail_supervisor_role else "FALSE",
        "has_sales_assistant_role": "TRUE" if has_sales_assistant_role else "FALSE",
    }


def enrich_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched_rows: list[dict[str, str]] = []

    for index, row in enumerate(rows, start=1):
        enriched_row = dict(row)
        resume_url = (row.get("resume_url") or "").strip()

        if not resume_url:
            enriched_row.update(empty_analysis())
            enriched_rows.append(enriched_row)
            print(f"[{index}] No resume URL, writing placeholder values.")
            continue

        try:
            pdf_bytes = download_resume(resume_url)
            text = extract_pdf_text(pdf_bytes)
            if not text.strip():
                enriched_row.update(empty_analysis())
                print(f"[{index}] Resume text was empty, writing placeholder values.")
            else:
                enriched_row.update(analyze_resume_text(text))
                print(f"[{index}] Processed resume successfully.")
        except Exception as error:  # noqa: BLE001
            enriched_row.update(empty_analysis())
            print(f"[{index}] Failed to process resume: {error}")

        enriched_rows.append(enriched_row)

    return enriched_rows


def write_output_csv(
    output_path: Path, fieldnames: list[str], rows: list[dict[str, str]]
) -> None:
    all_fieldnames = [*fieldnames, *[column for column in APPENDED_COLUMNS if column not in fieldnames]]
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    fieldnames, rows = read_csv_rows(input_path, args.limit)
    if not fieldnames:
        raise ValueError("Input CSV is missing a header row.")
    if "resume_url" not in fieldnames:
        raise ValueError("Input CSV must contain a 'resume_url' column.")

    enriched_rows = enrich_rows(rows)
    write_output_csv(output_path, fieldnames, enriched_rows)
    print(f"Wrote {len(enriched_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
