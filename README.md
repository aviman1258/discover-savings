# Discover-style savings app

A personal PWA: login screen, accounts list, and a savings transaction history.
Static data. Installs on a Pixel 10 as a real app — own launcher icon, no
address bar, works offline.

Zero dependencies. Plain HTML, CSS, and vanilla JS. No build step, no
`npm install`, no bundler. The scripts in `tools/` use the Python standard
library only.

Live at <https://aviman1258.github.io/discover-savings/>

---

# Adding transactions — step by step

The whole loop, start to finish. Roughly five minutes.

## 1. Edit the spreadsheet

Open **`data/discoversavings.xlsx`** — the copy inside this repo, *not* the one
in Downloads. Four columns:

| Date | Desc | Amount | Total |
|---|---|---|---|
| 8/14/2026 | ACH Deposit From Morgan Stanley | 4005.11 | 52303.84 |

- **Amount** is negative for money going out
- **Total** is the balance *after* that transaction
- Newest rows go at the **top**

**Fill in Total on every row you add.** The app displays your column D verbatim —
it doesn't compute balances. The rule your sheet follows:

```
Total(this row) = Total(row below) + Amount(this row)
```

## 2. Update D2 if you added anything newer

**`D2` is the current savings balance** — the figure on the accounts screen and
the anchor everything else is checked against. If your new top row changed the
balance, `D2` has to change with it.

## 3. Save it

`Ctrl+S`. You can leave Excel open — the scripts read a copy. But unsaved changes
are invisible to them, which is the most common way a run produces yesterday's
numbers.

## 4. Rebuild the ledger

```bash
cd C:/Users/achandra/source/repos/discover-savings
python tools/import_ledger.py
```

Expect something like:

```
  rows          69 across 16 months
  range         2025-05-01 .. 2026-08-14
  newest bal    52303.84  (from D2, matches config.js)
  minimum bal   9.17
```

**If it refuses to run**, it will say exactly what to fix. Most often:

```
FAIL: js/config.js savings balance is 44298.73 but the spreadsheet D2 says 52303.84
      -> set balance: '52303.84' on the savings line in js/config.js
```

Make that one edit in `js/config.js` and run it again. The accounts total
re-sums itself; it's never hardcoded.

**If it warns about column D**, it means your balances stopped reconciling
against the amounts. It names the rows. Only you can say which cell is wrong, so
it warns rather than blocking.

## 5. Check it

```bash
python tools/verify.py
```

23 checks. Catches what a browser won't show you until someone reads closely — a
balance column that doesn't add up, a total that disagrees with its parts, a file
the service worker promises but doesn't ship.

Don't deploy on a failure.

## 6. Bump the cache version

In **`sw.js`**, increment `CACHE_VERSION`:

```js
var CACHE_VERSION = 'v10';   // -> 'v11'
```

**This is not optional and it's the step people skip.** The service worker keeps
its own copy of every file on your phone — that's what makes the app work
offline. Without a bump it keeps serving the old copies forever and the update
looks like it did nothing.

## 7. Preview locally (optional)

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. Localhost runs **network-first**, so edits show up
on reload with no cache games.

## 8. Upload to GitHub

`git push` **does not work from this machine** — git is authenticated as
`achandra-costar` (work) while the repo belongs to `aviman1258` (personal), so
it 403s. Use the web uploader instead:

<https://github.com/aviman1258/discover-savings/upload/main>

Drag in whatever changed. For a transactions-only update that's:

```
sw.js        (file)     — the version bump
js           (folder)   — data.js, and config.js if the balance changed
```

Then **Commit changes** at the bottom.

Dragging a whole folder is fine and preserves paths. Same filenames overwrite.
Never drag `.git`.

## 9. Wait for the deploy

<https://github.com/aviman1258/discover-savings/actions>

A green tick means it's live, usually within a minute.

## 10. Refresh on the phone

**Force-close the app** — backgrounding it isn't enough:

> App switcher → swipe the Discover card away
> *or* long-press the icon → App info → Force stop

Then reopen it from the app drawer.

## 11. Confirm it took

Check the accounts screen shows the new total, and that your new rows are at the
top of the transaction list with the right balances.

**Still showing old numbers?** The worker is holding its cache. In Chrome on the
phone: three-dot → History → Clear browsing data → **Cached images and files**.
Then reopen. Rare after a version bump, but that's the fix.

---

# First-time install on the phone

Only needed once, or after the app icon changes.

1. Open <https://aviman1258.github.io/discover-savings/> in Chrome on the Pixel
2. It loads as a normal webpage with the address bar showing — **this is expected**
3. Three-dot menu → **Install app** (sometimes **Add to Home screen**)
4. Confirm. The icon lands in your app drawer.

Launch it from the drawer, not Chrome. That's where it goes full screen with no
address bar and gets its own card in the app switcher.

**If Chrome doesn't offer Install**, it's one of three things: the URL isn't
HTTPS, the service worker didn't register, or the manifest has an error. All
three show up in DevTools → Application before you ever pick up the phone.

**Changing the icon needs an uninstall and reinstall.** Android bakes it into the
installed package, so a version bump alone won't replace it. Long-press → App
info → Uninstall, then install again.

To test offline support: airplane mode, then launch from the drawer. It should
open with the full history.

---

# If this machine dies

Everything needed to rebuild and keep going is in this repo.

1. Download it — **Code → Download ZIP** on GitHub, or clone
2. Install Python 3. Nothing else: no Node, no npm, no pip packages
3. Pick up from step 1 above

**The workbook is in `data/`, not Downloads.** It used to live only in
`~/Downloads`, where a dead disk would have taken the one input the ledger is
built from. `import_ledger.py` still falls back to Downloads if the repo copy is
missing, and warns loudly if both exist and the Downloads one is newer — the
"edited the wrong file" trap.

`dist/` holds the source logos for the same reason: without them you can't
rebuild the icons or the wordmark.

## Nothing is ever actually lost

`js/data.js` **is** the ledger — every date, description, amount and balance.
Even with no spreadsheet at all, the data survives in the repo.

## Updating without a computer

You don't strictly need Python, or a PC. Both files can be edited in the browser
— including on a phone — with GitHub's pencil icon:

- `js/data.js` — add rows at the top, newest first
- `sw.js` — bump `CACHE_VERSION`

Commit, wait for Pages, force-close the app. The catch: nothing checks your
arithmetic. Each row's `balance` must equal the row above it minus that row's
`amount`, and the newest must match the savings balance in `js/config.js`.
`verify.py` normally enforces both.

---

# Reference

## Two things to know

**This is public.** GitHub Pages needs a public repo on a free account. Anyone
with the URL can read the source, credentials included. Fine for an obscure URL;
it is not private. Making the repo private on a free plan switches Pages off
entirely — and even on a paid plan the *site* stays public.

**The login is not security.** It's a UI state machine — a string comparison in
`js/config.js`. The fingerprint option is real WebAuthn and the OS genuinely
checks your thumb, but with no server nothing verifies the result. Don't grow
either into something that guards anything real.

Credentials: **`achandra`** / **`200Free`** (change in `js/config.js`).

## The scripts

```bash
python tools/import_ledger.py   # data/discoversavings.xlsx -> js/data.js
python tools/build_assets.py    # dist/*.png -> img/wordmark.png + icons/*.png
python tools/verify.py          # pre-deploy checks
python -m http.server 8080      # local preview
```

`build_assets.py` only needs re-running if you replace the source logos.

## Layout

```
index.html                 six views, swapped by toggling [hidden]
css/app.css                all styling; palette as custom properties in :root
js/config.js               credentials, accounts, balances, support number
js/data.js                 GENERATED — do not hand-edit
js/app.js                  routing, login, rendering, search, session
manifest.webmanifest
sw.js                      cache-first service worker; CACHE_VERSION lives here
icons/                     192, 512, maskable-512
img/                       the wordmark, black and white variants
data/                      the source spreadsheet — edit this one
dist/                      source logos, not served
tools/                     import_ledger, build_assets, verify
```

Single page with JS view switching rather than six HTML files. Real page loads
flash white between screens in an installed PWA, which gives away the web view.

All asset paths are relative and the manifest's `start_url`/`scope` are `.`,
because Pages serves this from a subpath. An absolute path like `/css/app.css`
resolves to the domain root and 404s — invisible on localhost, broken in
production. `verify.py` checks for this.

## Notes

**The spreadsheet is the source of truth, column D included.** Balances are read
straight from it rather than computed, so the app shows your figures, not the
script's arithmetic.

**Two date corrections live in `import_ledger.py`, not the workbook** — an
interest row dated a year late, and a withdrawal that couldn't have cleared on
its stated date. They're keyed by content, not row number, so inserting rows
doesn't misapply them. See `DATE_FIXES`. Fix them in the sheet and the script
just reports them as skipped.

**The palette was confirmed by eye against the real app.** Discover has never
published official hex values — the aggregator sites say so outright and
disagree with each other (`#E55C20` vs `#EA4209`). Every colour is a custom
property at the top of `css/app.css`. `--fdic-navy` is a regulated value; leave
it alone.

**The FDIC digital sign is required**, not decoration — `12 CFR 328.5`. The
wording is prescribed verbatim, em dash included. Don't reword it. It switches
to white lettering on the navy login and in dark mode, which the regulation
allows where navy would be illegible.

**There is no opening balance.** The list is the most recent page of activity,
not the life of the account. The oldest row is simply where the data stops.

**The logos are Discover's.** `dist/` holds the originals; `build_assets.py`
recolours the wordmark and builds the three icon sizes. Fine for a personal
mockup, but this repo is public — worth remembering you're serving someone
else's trademark from it.

**Forward navigation pauses on a spinner** (350–800ms, longer for login, a
random 2–5s for a transfer or deposit). Back is instant on purpose: delaying a
`popstate` leaves the history entry changed while the old screen is still up.
