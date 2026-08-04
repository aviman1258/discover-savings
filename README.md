# Discover-style savings app

A personal PWA: login screen, accounts list, and a savings transaction history.
Static data. Installs on a Pixel 10 as a real app — own launcher icon, no
address bar, works offline.

Zero dependencies. Plain HTML, CSS, and vanilla JS. No build step, no
`npm install`, no bundler. The two Python scripts in `tools/` use the standard
library only.

## Two things to know

**This is public.** GitHub Pages requires a public repo on a free account.
Anyone with the URL can read the source, including the credentials below. Fine
for an obscure URL; it is not private.

**The login is not security.** It's a UI state machine — a string comparison in
`js/config.js`. Don't grow it into something that guards anything real.

## Run it locally

```bash
python -m http.server 8080
```

Then open <http://localhost:8080>.

`localhost` counts as a secure origin, so the service worker registers and
Chrome offers **Install** — the whole PWA path is testable without deploying.

On `localhost` and `127.0.0.1` the service worker runs **network-first**, so
editing a file and reloading just works. Everywhere else it's cache-first. Without
that split, local edits appear to do nothing because the worker keeps handing your
old files back.

**If the browser still shows something you've already changed**, the worker is
serving a stale copy. Fix it with DevTools → Application → Storage →
**Clear site data**, then reload.

Credentials: **`achandra`** / **`200Free`** (change in `js/config.js`).

## Updating the data

The ledger is generated from a spreadsheet, not hand-edited:

```bash
python tools/import_ledger.py   # ~/Downloads/discoversavings.xlsx -> js/data.js
python tools/build_assets.py    # dist/*.png -> img/wordmark.png + icons/*.png
```

**The spreadsheet is the source of truth, column D included.** Balances are taken
straight from column D rather than computed, so the app shows your own figures.

`import_ledger.py` refuses to run if cell `D2` disagrees with the savings balance
in `js/config.js`, since both appear on screen. It warns — but doesn't block — when
column D stops reconciling against the amounts, because only you can say which
cell is wrong. Two date corrections live in the script rather than the workbook, so
your file stays untouched; see the `DATE_FIXES` block for what and why.

## Deploying

```bash
git push -u origin main
```

Then on GitHub: **Settings → Pages → Source: Deploy from a branch → `main` /
`(root)` → Save.** Live at
<https://aviman1258.github.io/discover-savings/> in a minute or two.

All asset paths are relative and the manifest's `start_url`/`scope` are `.`,
because Pages serves this from a subpath. An absolute path like `/css/app.css`
would resolve to the domain root and 404.

### ⚠️ Bump `CACHE_VERSION` after every deploy

**In `sw.js`, increment `CACHE_VERSION` whenever you change any file.**

The service worker keeps its own copy of every asset on the phone — that's what
makes the app work offline. It also means that without a version bump, the
installed app will keep serving the **old** files indefinitely. This is the
single most common reason a PWA looks like it didn't update.

If you hit a stale app: force-close and reopen it, twice if needed.

Changing the **icon or name** after installing often doesn't take either, since
Android baked those into the installed package. Uninstall and reinstall.

## Installing on the Pixel

1. Open the Pages URL in Chrome on the phone
2. It loads as a normal webpage, address bar and all — this is expected
3. Three-dot menu → **Install app** (sometimes **Add to Home screen**)
4. Confirm. The icon lands in your app drawer.

Launch it from the drawer, not Chrome. That's where the difference shows: full
screen, no address bar, its own card in the app switcher.

If Chrome doesn't offer Install, it's one of three things: the URL isn't HTTPS,
the service worker didn't register, or the manifest has an error. All three are
visible in DevTools → Application before you ever pick up the phone.

To remove: long-press the icon → App info → Uninstall.

## Layout

```
index.html                 six views, swapped by toggling [hidden]
css/app.css                all styling; palette as custom properties in :root
js/config.js               credentials, accounts, balances, support number
js/data.js                 GENERATED — do not hand-edit
js/app.js                  routing, login, rendering, search, session
manifest.webmanifest
sw.js                      cache-first service worker
icons/                     192, 512, maskable-512
img/wordmark.png           the wordmark, recoloured white
tools/import_ledger.py     spreadsheet -> js/data.js
tools/build_assets.py      dist/*.png -> wordmark + icons (stdlib PNG codec)
dist/                      source logos, not served
```

Single page with JS view switching rather than three HTML files. Real page loads
flash white between screens in an installed PWA, which gives away the web view.

## Notes

**The palette was confirmed by eye against the real app.** Worth knowing that
Discover has never published official hex values — the aggregator sites say so
outright, and they disagree with each other (`#E55C20` vs `#EA4209`). Every colour
is a custom property at the top of `css/app.css`, so changing one is a one-line
edit. `--fdic-navy` is a regulated value; leave it alone.

**The FDIC digital sign is required**, not decoration — `12 CFR 328.5`. The
wording is prescribed verbatim, em dash included. Don't reword it.

**There is no opening balance.** The list is the most recent page of activity,
not the life of the account. The oldest row is simply where the data stops.

**The logos are Discover's.** `dist/` holds the originals; `build_assets.py`
recolours the wordmark white and builds the three icon sizes from the app icon.
Fine for a personal mockup, but this repo is public — worth remembering that
you're serving someone else's trademark from it.

**Forward navigation pauses on a spinner** (350–800ms, longer for login, and a
random 2–5s when scheduling a transfer). Back is instant on purpose: delaying a
`popstate` leaves the history entry changed while the old screen is still up.
