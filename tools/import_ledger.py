#!/usr/bin/env python3
"""Read discoversavings.xlsx and write js/data.js.

Standard library only -- no openpyxl, no pandas. An .xlsx is a zip of XML, so
zipfile + ElementTree is all it takes.

Re-runnable: edit the spreadsheet, run this again, get a fresh data.js.

THE SPREADSHEET IS THE SOURCE OF TRUTH, column D included. Balances are taken
straight from column D rather than computed, so what the app shows is what the
workbook says. Where a row has no D value the balance is carried forward from the
row above, which is the only arithmetic left.

Two checks remain. D2 must match the savings balance in js/config.js, because
both appear on screen and a mismatch would be visible. And column D is checked
for self-consistency -- each row's balance minus its amount should equal the next
row's balance -- reported as a warning, since only you can say which cell is
wrong when it doesn't.
"""

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    """Excel writes 41599.88 as 41599.879999999997. Quantise to cents.

    Kept as Decimal throughout rather than float, so the numbers written into
    data.js are exact to the cent.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Excel's 1900 date system counts from this epoch for all dates after 1900-03-01.
EXCEL_EPOCH = datetime.date(1899, 12, 30)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
XLSX = os.path.join(os.path.expanduser("~"), "Downloads", "discoversavings.xlsx")
OUT = os.path.join(PROJECT, "js", "data.js")
CONFIG = os.path.join(PROJECT, "js", "config.js")

# Corrections agreed with the user.
#
# Keyed by CONTENT, not spreadsheet row number. Row numbers shift the moment a
# row is inserted above them, and a fix keyed to row 48 would silently start
# rewriting the date of whatever transaction landed there instead.
#
#   Interest Paid 10.56 was dated 2026-09-30: a future date, out of sequence.
#     Every other interest row lands on a month end. Year typo.
#   ROBINHOOD -760 was dated 2026-05-13, but the balance that day was $11.52 so
#     the withdrawal could not clear. The sheet's own row order already placed
#     it after the 05-28 deposit.
DATE_FIXES = [
    ((datetime.date(2026, 9, 30), "Interest Paid", Decimal("10.56")),
     datetime.date(2025, 9, 30)),
    ((datetime.date(2026, 5, 13), "ACH Withdrawal ROBINHOOD Funds", Decimal("-760")),
     datetime.date(2026, 5, 29)),
]


def serial_to_date(serial):
    return EXCEL_EPOCH + datetime.timedelta(days=int(serial))


def read_sheet(path):
    """Return (transactions, closing_balance_from_D2).

    transactions is a list of dicts with date, description, amount.
    """
    with zipfile.ZipFile(path) as book:
        strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                strings.append("".join(t.text or "" for t in si.iter(NS + "t")))

        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))

    rows = []
    closing = None

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

        # D on the first data row is the current savings balance and becomes the
        # anchor. On later rows it's the user's own running balance, which we
        # keep as a free independent check -- see check_against_column_d.
        sheet_balance = money(cells["D"]) if cells.get("D") else None
        if closing is None and sheet_balance is not None:
            closing = sheet_balance

        rows.append({
            "date": serial_to_date(cells["A"]),
            "description": cells["B"],
            "amount": money(cells["C"]),
            "sheet_balance": sheet_balance,
        })

    return rows, closing


def config_savings_balance():
    """Pull the savings balance out of js/config.js."""
    text = open(CONFIG, encoding="utf-8").read()
    for line in text.splitlines():
        if "kind: 'savings'" in line:
            found = re.search(r"balance:\s*'([\d.]+)'", line)
            if found:
                return Decimal(found.group(1))
    return None


def apply_fixes(rows):
    for (wrong_date, description, amount), corrected in DATE_FIXES:
        hits = [r for r in rows
                if r["date"] == wrong_date
                and r["description"] == description
                and r["amount"] == amount]
        if not hits:
            # Not an error: the user may have corrected the sheet themselves, or
            # removed the row. Say so rather than failing.
            print("  fix skipped (no match): %s %s %s"
                  % (wrong_date, description, amount))
            continue
        for row in hits:
            row["date"] = corrected
        print("  fix applied: %s %s -> %s" % (description, wrong_date, corrected))


def build_ledger(rows, closing):
    """Sort newest first and attach the balance shown against each row.

    Column D wins wherever it's populated -- the workbook is the source of truth,
    so the app displays the user's own figures rather than our arithmetic. Rows
    without a D value get the balance carried down from the row above them.
    """
    # Stable, so same-day rows keep their spreadsheet order.
    rows.sort(key=lambda r: r["date"], reverse=True)

    carried = closing
    for row in rows:
        if row["sheet_balance"] is not None:
            row["balance"] = row["sheet_balance"]
        else:
            row["balance"] = carried
        # What the row above leaves behind, for the next row lacking a D value.
        carried = row["balance"] - row["amount"]

    return rows


def column_d_breaks(rows):
    """Find places where column D doesn't reconcile with the amounts.

    For any two adjacent rows, the older row's balance should equal the newer
    row's balance minus the newer row's amount. Where it doesn't, one of those
    two D cells is wrong -- or the amount between them is. The script can't know
    which, so it reports and leaves the call to the user.

    This is the check that matters now that balances come straight from column D:
    a break here shows up in the app as a balance that jumps by more or less than
    the transaction next to it.
    """
    breaks = []
    for newer, older in zip(rows, rows[1:]):
        if newer["balance"] is None or older["balance"] is None:
            continue
        expected = newer["balance"] - newer["amount"]
        if expected != older["balance"]:
            breaks.append((newer, older, expected - older["balance"]))
    return breaks


def check(rows, closing, config_balance):
    """Return (problems, warnings).

    Problems block the write: the ledger would be broken or would visibly
    contradict itself on screen. Warnings are things worth knowing that the user
    may well have decided deliberately.
    """
    problems = []
    warnings = []

    if not rows:
        return ["no transactions parsed"], warnings

    if closing is None:
        problems.append("cell D2 is empty -- it must hold the current savings balance")
        return problems, warnings

    # The one comparison that can actually fail, and the one that matters: the
    # spreadsheet's closing balance versus the figure the app displays. Both
    # appear on screen, so a mismatch is visible.
    if config_balance is None:
        problems.append("could not find the savings balance in js/config.js")
    elif config_balance != closing:
        problems.append(
            "js/config.js savings balance is %s but the spreadsheet D2 says %s\n"
            "         -> set balance: '%s' on the savings line in js/config.js"
            % (config_balance, closing, closing)
        )

    negative = [r for r in rows if r["balance"] < 0]
    if negative:
        problems.append(
            "%d row(s) carry a negative balance, first at %s (%s).\n"
            "         Either an amount is wrong, D2 is too low, or a deposit is missing."
            % (len(negative), negative[0]["date"], negative[0]["balance"])
        )

    for older, newer in zip(rows[1:], rows):
        if older["date"] > newer["date"]:
            problems.append("not date-descending: %s after %s"
                            % (older["date"], newer["date"]))
            break

    # A warning, not a problem: the workbook is authoritative, and only you can
    # say which of the two cells around a break is the wrong one.
    breaks = column_d_breaks(rows)
    if breaks:
        lines = []
        for newer, older, gap in breaks[:6]:
            lines.append(
                "           %s %-40s balance %10s, amount %10s\n"
                "           %s %-40s balance %10s  <- %s off"
                % (newer["date"], newer["description"][:40], newer["balance"], newer["amount"],
                   older["date"], older["description"][:40], older["balance"], gap))
        warnings.append(
            "column D doesn't reconcile at %d place(s) out of %d. The app shows\n"
            "           column D verbatim, so the balance there will appear to jump by\n"
            "           more or less than the transaction beside it:\n%s%s"
            % (len(breaks), len(rows) - 1, "\n".join(lines),
               "\n           ..." if len(breaks) > 6 else ""))

    return problems, warnings


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

    lock = os.path.join(os.path.dirname(XLSX), "~$" + os.path.basename(XLSX))
    if os.path.exists(lock):
        print("  note: the workbook is open in Excel. If you just made changes,")
        print("        save it (Ctrl+S) or they won't be picked up.\n")

    print("reading %s" % XLSX)
    rows, closing = read_sheet(XLSX)
    apply_fixes(rows)
    rows = build_ledger(rows, closing)

    config_balance = config_savings_balance()
    problems, warnings = check(rows, closing, config_balance)

    for warning in warnings:
        print("  warning: %s" % warning)
    if warnings:
        print("")

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
    print("  newest bal    %s  (from D2, matches config.js)" % rows[0]["balance"])
    print("  oldest bal    %s" % rows[-1]["balance"])
    print("  minimum bal   %s" % min(r["balance"] for r in rows))
    print("")
    print("wrote %s" % OUT)
    print("\nremember: bump CACHE_VERSION in sw.js so the phone picks this up")


if __name__ == "__main__":
    main()
