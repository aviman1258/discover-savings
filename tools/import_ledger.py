#!/usr/bin/env python3
"""Read discoversavings.xlsx and write js/data.js.

Standard library only -- no openpyxl, no pandas. An .xlsx is a zip of XML, so
zipfile + ElementTree is all it takes.

Re-runnable: edit the spreadsheet, run this again, get a fresh data.js.

The two date corrections below are applied here rather than in the spreadsheet,
so the source file stays untouched and the fixes are visible in code.
"""

import datetime
import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Excel's 1900 date system counts from this epoch for all dates after 1900-03-01.
EXCEL_EPOCH = datetime.date(1899, 12, 30)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
XLSX = os.path.join(os.path.expanduser("~"), "Downloads", "discoversavings.xlsx")
OUT = os.path.join(PROJECT, "js", "data.js")

# The savings balance after the newest transaction. Everything is computed
# backwards from here, so it is the one figure that must be right.
CLOSING_BALANCE = Decimal("2698.85")

# Corrections agreed with the user. Keyed by spreadsheet row number.
#
#   48 - "Interest Paid" was dated 2026-09-30: two months in the future and out
#        of sequence in the sheet. Every other interest row lands on a month end,
#        and it sits between 2025-10-03 and 2025-09-21. Year typo.
#   11 - "ROBINHOOD Funds -760" was dated 2026-05-13, but the balance on that day
#        was $11.52 so the withdrawal could not clear. The sheet's own row order
#        already placed it after the 05-28 deposit.
DATE_FIXES = {
    48: datetime.date(2025, 9, 30),
    11: datetime.date(2026, 5, 29),
}


def serial_to_date(serial):
    return EXCEL_EPOCH + datetime.timedelta(days=int(serial))


def read_rows(path):
    """Yield (sheet_row_number, date, description, amount) from the workbook."""
    with zipfile.ZipFile(path) as book:
        strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                strings.append("".join(t.text or "" for t in si.iter(NS + "t")))

        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))

    for row in sheet.iter(NS + "row"):
        cells = {}
        for cell in row.findall(NS + "c"):
            column = "".join(ch for ch in cell.get("r") if ch.isalpha())
            value = cell.find(NS + "v")
            if value is None:
                continue
            if cell.get("t") == "s":
                cells[column] = strings[int(value.text)]
            else:
                cells[column] = value.text

        # Column A holds an Excel date serial. The header row has text there,
        # which is how we skip it without hardcoding a row number.
        if not cells.get("A", "").isdigit():
            continue
        if not cells.get("B") or not cells.get("C"):
            continue

        number = int(row.get("r"))
        yield number, serial_to_date(cells["A"]), cells["B"], Decimal(cells["C"])


def build_ledger(raw):
    """Apply fixes, sort newest first, attach running balances."""
    rows = []
    for number, date, description, amount in raw:
        rows.append(
            {
                "row": number,
                "date": DATE_FIXES.get(number, date),
                "description": description,
                "amount": amount,
            }
        )

    applied = sorted(n for n in DATE_FIXES if any(r["row"] == n for r in rows))
    for number in applied:
        print("  fix: row %d date -> %s" % (number, DATE_FIXES[number]))

    # Newest first, matching how a bank app lists activity. Stable, so
    # same-day rows keep their spreadsheet order.
    rows.sort(key=lambda r: r["date"], reverse=True)

    # The running balance on a row is the balance *after* that transaction
    # posted. Walking backwards from the closing balance: subtract each row's
    # amount to get the balance the row below it left behind.
    balance = CLOSING_BALANCE
    for row in rows:
        row["balance"] = balance
        balance -= row["amount"]

    return rows


def check(rows):
    """Fail loudly rather than ship a ledger whose column does not add up."""
    problems = []

    if not rows:
        problems.append("no transactions parsed")
        return problems

    if rows[0]["balance"] != CLOSING_BALANCE:
        problems.append(
            "newest balance is %s, expected %s" % (rows[0]["balance"], CLOSING_BALANCE)
        )

    negative = [r for r in rows if r["balance"] < 0]
    if negative:
        problems.append(
            "%d row(s) carry a negative balance, first at %s (%s)"
            % (len(negative), negative[0]["date"], negative[0]["balance"])
        )

    for older, newer in zip(rows[1:], rows):
        if older["date"] > newer["date"]:
            problems.append(
                "not date-descending: %s appears after %s"
                % (older["date"], newer["date"])
            )
            break

    return problems


def write_data_js(rows, path):
    records = [
        {
            "date": r["date"].isoformat(),
            "description": r["description"],
            "amount": str(r["amount"]),
            "balance": str(r["balance"]),
        }
        for r in rows
    ]

    body = ",\n".join("  " + json.dumps(r) for r in records)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "// GENERATED by tools/import_ledger.py -- do not hand-edit.\n"
            "// Source: ~/Downloads/discoversavings.xlsx\n"
            "// Amounts and balances are strings so no float rounding can creep in;\n"
            "// the UI formats them and never does arithmetic on them.\n"
            "//\n"
            "// Newest first. `balance` is the balance after that transaction posted.\n"
            "// The oldest row is where the app stops loading, NOT where the account\n"
            "// opened -- there is no opening balance.\n"
            "window.TRANSACTIONS = [\n"
        )
        handle.write(body)
        handle.write("\n];\n")


def main():
    if not os.path.exists(XLSX):
        sys.exit("spreadsheet not found: %s" % XLSX)

    print("reading %s" % XLSX)
    rows = build_ledger(read_rows(XLSX))

    problems = check(rows)
    if problems:
        for problem in problems:
            print("  FAIL: %s" % problem, file=sys.stderr)
        sys.exit(1)

    credits = sum(r["amount"] for r in rows if r["amount"] > 0)
    debits = sum(r["amount"] for r in rows if r["amount"] < 0)
    months = len({(r["date"].year, r["date"].month) for r in rows})

    write_data_js(rows, OUT)

    print("")
    print("  rows          %d across %d months" % (len(rows), months))
    print("  range         %s .. %s" % (rows[-1]["date"], rows[0]["date"]))
    print("  credits       %s" % credits)
    print("  debits        %s" % debits)
    print("  net           %s" % (credits + debits))
    print("  newest bal    %s" % rows[0]["balance"])
    print("  oldest bal    %s" % rows[-1]["balance"])
    print("  minimum bal   %s" % min(r["balance"] for r in rows))
    print("")
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
