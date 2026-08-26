#!/usr/bin/env python3
"""Check the app hangs together before you deploy it.

Standard library only. Run after any change:

    python tools/verify.py

Catches the things that are invisible in a browser until someone reads closely:
a balance column that doesn't add up, a total that disagrees with its parts, an
asset the service worker promises but doesn't ship, an absolute path that works
locally and 404s on GitHub Pages.

Exit code 0 means everything passed.
"""

import json
import os
import re
import struct
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

failures = []
notes = []


def read(rel):
    with open(os.path.join(PROJECT, rel), encoding="utf-8") as handle:
        return handle.read()


def check(label, actual, expected):
    if actual != expected:
        failures.append("%s: got %r, expected %r" % (label, actual, expected))
    else:
        notes.append("%s = %s" % (label, actual))


def fail(message):
    failures.append(message)


# --- parse the two JS data files -------------------------------------------
# config.js is a JS object literal, so it gets picked apart with regexes rather
# than parsed. data.js is a JSON array behind an assignment, so it can be sliced
# out and parsed properly.

def load_accounts():
    text = read("js/config.js")
    start = text.index("accounts:")
    block = text[start:text.index("]", start)]

    accounts = []
    for chunk in block.split("{")[1:]:
        entry = {}
        for field in ("id", "kind", "name", "mask", "balance", "apy", "rate", "maturity"):
            found = re.search(field + r":\s*'([^']*)'", chunk)
            if found:
                entry[field] = found.group(1)
        if entry.get("id"):
            accounts.append(entry)
    return accounts


def load_credentials():
    text = read("js/config.js")
    user = re.search(r"userId:\s*'([^']*)'", text)
    password = re.search(r"password:\s*'([^']*)'", text)
    return (user.group(1) if user else None,
            password.group(1) if password else None)


def load_ledger():
    text = read("js/data.js")
    return json.loads(text[text.index("["):text.rindex("]") + 1])


def money(value):
    """Format cents-as-Decimal for display, with thousands separators."""
    return "$" + "{:,.2f}".format(value)


# --- checks -----------------------------------------------------------------

def check_money():
    accounts = load_accounts()
    ledger = load_ledger()

    total = sum(Decimal(a["balance"]) for a in accounts)
    notes.append("accounts total = %s across %d accounts"
                 % (money(total), len(accounts)))

    savings = [a for a in accounts if a["kind"] == "savings"]
    if len(savings) != 1:
        fail("expected exactly one savings account, found %d" % len(savings))
        return
    savings = savings[0]

    if not ledger:
        fail("ledger is empty")
        return

    # The savings balance appears on two screens, and the newest row's running
    # balance is the same number a third time. All three must agree.
    newest = Decimal(ledger[0]["balance"])
    if Decimal(savings["balance"]) != newest:
        fail("savings balance is %s but the newest ledger row says %s"
             % (money(Decimal(savings["balance"])), money(newest)))
    else:
        notes.append("savings balance matches the newest ledger row = %s" % money(newest))

    notes.append("ledger: %d rows, %s .. %s"
                 % (len(ledger), ledger[-1]["date"], ledger[0]["date"]))

    # Each row's balance minus its amount must equal the next (older) row's.
    breaks = 0
    for newer, older in zip(ledger, ledger[1:]):
        expected = Decimal(newer["balance"]) - Decimal(newer["amount"])
        if expected != Decimal(older["balance"]):
            breaks += 1
            if breaks <= 3:
                fail("balance break at %s -> %s: expected %s, got %s"
                     % (newer["date"], older["date"],
                        money(expected), money(Decimal(older["balance"]))))
    if breaks == 0:
        notes.append("running balance reconciles across all %d rows" % len(ledger))
    elif breaks > 3:
        fail("...and %d more balance breaks" % (breaks - 3))

    negative = [r for r in ledger if Decimal(r["balance"]) < 0]
    check("rows with a negative balance", len(negative), 0)

    zero = [r for r in ledger if Decimal(r["amount"]) == 0]
    check("rows with a zero amount", len(zero), 0)

    out_of_order = [(a["date"], b["date"]) for a, b in zip(ledger, ledger[1:])
                    if a["date"] < b["date"]]
    check("out-of-order rows", len(out_of_order), 0)

    months = {r["date"][:7] for r in ledger}
    notes.append("month groups = %d" % len(months))

    # Every CD popup shows three figures; a missing one renders as "undefined%".
    for cd in [a for a in accounts if a["kind"] == "cd"]:
        for field in ("apy", "rate", "maturity"):
            if not cd.get(field):
                fail("CD ••••%s has no %s" % (cd["mask"], field))
        if cd.get("maturity") and not re.match(r"^\d{4}-\d{2}-\d{2}$", cd["maturity"]):
            fail("CD ••••%s maturity should be ISO, got %s" % (cd["mask"], cd["maturity"]))
    notes.append("all CDs carry APY, rate and maturity")

    user, password = load_credentials()
    if not user or not password:
        fail("credentials missing from config.js")
    else:
        notes.append("credentials = %s / %s" % (user, password))


def check_wiring():
    html = read("index.html")
    app = read("js/app.js")

    ids = set(re.findall(r'\sid="([^"]+)"', html))
    wanted = set(re.findall(r"\$\('([^']+)'\)", app))
    missing = sorted(wanted - ids)
    if missing:
        fail("app.js reads elements that don't exist: " + ", ".join(missing))
    else:
        notes.append("all %d element ids app.js reads exist in the markup" % len(wanted))

    for view in ("login", "accounts", "transactions", "alerts", "transfer", "deposit"):
        if 'id="view-%s"' % view not in html:
            fail("missing view: view-" + view)
    notes.append("all six views present")

    # capture="environment" is what opens the rear camera instead of a file
    # browser. Scoped to real <input> tags -- the explanatory comment nearby
    # contains the same literal.
    captures = len(re.findall(r'<input[^>]*capture="environment"', html))
    check("camera capture inputs", captures, 2)


def check_paths():
    html = read("index.html")
    sw = read("sw.js")

    # Pages serves from a subpath, so a leading slash resolves to the domain
    # root and 404s. This is invisible on localhost.
    absolute = re.findall(r'(?:href|src)="(/[^"]*)"', html)
    if absolute:
        fail("absolute paths in index.html will 404 on Pages: " + ", ".join(absolute))
    else:
        notes.append("all markup asset paths are relative")

    manifest = json.loads(read("manifest.webmanifest"))
    check("manifest start_url", manifest["start_url"], ".")
    check("manifest scope", manifest["scope"], ".")
    check("manifest display", manifest["display"], "standalone")
    if "maskable" not in [i.get("purpose") for i in manifest["icons"]]:
        fail("manifest has no maskable icon")

    # Every file the worker promises to cache has to exist, or install() rejects
    # and the app silently loses offline support.
    listed = [p.strip("'") for p in re.findall(r"'\./[^']*'", sw)]
    for rel in listed:
        rel = rel[2:]
        if rel and not os.path.exists(os.path.join(PROJECT, rel)):
            fail("sw.js caches %s but the file is missing" % rel)
    notes.append("sw.js precache list: %d entries, all present" % len(listed))

    version = re.search(r"CACHE_VERSION = '([^']+)'", sw)
    notes.append("CACHE_VERSION = %s" % (version.group(1) if version else "MISSING"))
    if not version:
        fail("sw.js has no CACHE_VERSION")


def png_size(rel):
    path = os.path.join(PROJECT, rel)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        head = handle.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def check_assets():
    for rel, expected in (("icons/icon-192.png", 192),
                          ("icons/icon-512.png", 512),
                          ("icons/icon-maskable-512.png", 512)):
        size = png_size(rel)
        if size is None:
            fail("missing or unreadable: " + rel)
        elif size != (expected, expected):
            fail("%s should be %dx%d, got %dx%d" % (rel, expected, expected, size[0], size[1]))
    notes.append("icons present at the sizes the manifest declares")

    mark = png_size("img/wordmark.png")
    source = png_size("dist/Discover-logo-main.png")
    if mark is None:
        fail("missing img/wordmark.png")
    elif source and (mark[0] >= source[0] or mark[1] >= source[1]):
        # The source is a solid white rectangle. If trimming found nothing, the
        # background is still there and the letters are white-on-white.
        fail("wordmark wasn't trimmed (%dx%d vs source %dx%d): its white "
             "background is still attached" % (mark + source))
    else:
        notes.append("wordmark trimmed to %dx%d, white background cut away" % mark)


def check_fdic():
    html = read("index.html")
    css = read("css/app.css")

    # 12 CFR 328.5 prescribes this string. The em dash is part of it.
    required = ("FDIC-Insured&mdash;Backed by the full faith and credit "
                "of the U.S. Government")
    if required not in html:
        fail("FDIC statement doesn't match the regulation verbatim")
    else:
        notes.append("FDIC statement matches 12 CFR 328.5 verbatim")

    if "#003256" not in css:
        fail("FDIC navy #003256 missing from the stylesheet")

    # The sign has to stay legible on the navy login and in dark mode; the
    # regulation allows white lettering exactly for this.
    if ".view--navy .fdic__mark" not in css or "body.dark .fdic__mark" not in css:
        fail("FDIC sign has no white variant for navy or dark backgrounds")
    else:
        notes.append("FDIC sign switches to white where navy would be illegible")


def main():
    for step in (check_money, check_wiring, check_paths, check_assets, check_fdic):
        try:
            step()
        except Exception as error:      # a crash here is itself a failure
            failures.append("%s crashed: %s" % (step.__name__, error))

    for note in notes:
        print("  ok    %s" % note)

    if failures:
        print("")
        for problem in failures:
            print("  FAIL  %s" % problem, file=sys.stderr)
        print("\n%d check(s) failed" % len(failures))
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
