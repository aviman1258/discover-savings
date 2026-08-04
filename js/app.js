/* Discover-style savings app.
 *
 * Five views in one document, swapped by toggling [hidden]. A real page load
 * between screens flashes white in an installed PWA, which is one of the
 * clearest tells that you're looking at a web view.
 */
(function () {
  'use strict';

  var CFG = window.CONFIG;
  var TX = window.TRANSACTIONS || [];

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

  var STORE_SESSION = 'ds.session';
  var STORE_USER = 'ds.userId';
  var STORE_THEME = 'ds.theme';

  var $ = function (id) { return document.getElementById(id); };

  /* Money ------------------------------------------------------------------
   * Amounts arrive as strings and are parsed to integer cents before any
   * arithmetic, so floating point never touches the numbers. $0.01 drift in a
   * balance column is exactly the kind of thing that breaks the illusion.
   */

  function cents(value) {
    var text = String(value).trim();
    var negative = text.charAt(0) === '-';
    if (negative) text = text.slice(1);

    var parts = text.split('.');
    var whole = parseInt(parts[0] || '0', 10);
    var frac = ((parts[1] || '') + '00').slice(0, 2);
    var total = whole * 100 + parseInt(frac, 10);

    return negative ? -total : total;
  }

  function money(amount) {
    var value = Math.abs(amount);
    var dollars = String(Math.floor(value / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    var pennies = String(value % 100);
    if (pennies.length < 2) pennies = '0' + pennies;
    return '$' + dollars + '.' + pennies;
  }

  /* Dates ------------------------------------------------------------------
   * Parsed by splitting the string, not with new Date('2026-08-03'). That form
   * is treated as UTC midnight and shifts to the previous day in any negative
   * timezone -- so every date would render one day early.
   */

  function parts(iso) {
    var bits = iso.split('-');
    return { y: +bits[0], m: +bits[1], d: +bits[2] };
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function usDate(iso) {
    var p = parts(iso);
    return pad2(p.m) + '/' + pad2(p.d) + '/' + p.y;
  }

  function monthLabel(iso) {
    var p = parts(iso);
    return (MONTHS[p.m - 1] + ' ' + p.y).toUpperCase();
  }

  function longDate(iso) {
    var p = parts(iso);
    return MONTHS[p.m - 1] + ' ' + p.d + ', ' + p.y;
  }

  /* Shared fragments ------------------------------------------------------- */

  function fillTemplates() {
    var wordmark = $('tpl-wordmark');
    var fdic = $('tpl-fdic');

    // One wordmark variant covers both places it appears -- it's white, and it
    // only ever sits on navy or orange.
    document.querySelectorAll('[data-wordmark]').forEach(function (host) {
      host.appendChild(wordmark.content.cloneNode(true));
    });

    document.querySelectorAll('[data-fdic]').forEach(function (host) {
      host.appendChild(fdic.content.cloneNode(true));
    });

    document.querySelectorAll('[data-foot]').forEach(function (host) {
      host.textContent = CFG.bankName + ', Member FDIC';
    });
  }

  /* Theme ------------------------------------------------------------------
   * Every colour is a CSS custom property, so flipping one class on <body> is
   * the entire implementation. The login screen stays navy in both modes.
   */

  function applyTheme(dark) {
    document.body.classList.toggle('dark', dark);
    var button = $('theme-toggle');
    if (button) {
      button.setAttribute('aria-label',
        dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
  }

  function initTheme() {
    var saved = localStorage.getItem(STORE_THEME);
    var dark;
    if (saved) {
      dark = saved === 'dark';
    } else {
      // No preference stored yet: follow the phone's system setting.
      dark = window.matchMedia
        && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    applyTheme(!!dark);

    $('theme-toggle').addEventListener('click', function () {
      var next = !document.body.classList.contains('dark');
      applyTheme(next);
      localStorage.setItem(STORE_THEME, next ? 'dark' : 'light');
    });
  }

  /* Routing ---------------------------------------------------------------
   * Every view and the modal are history entries, so Android's back gesture
   * navigates instead of closing the app. Forgetting this is easy and it feels
   * broken the first time you swipe.
   */

  var VIEWS = {
    login: $('view-login'),
    accounts: $('view-accounts'),
    transactions: $('view-transactions'),
    alerts: $('view-alerts'),
    transfer: $('view-transfer'),
    deposit: $('view-deposit')
  };

  var shownView = null;

  function apply(state) {
    Object.keys(VIEWS).forEach(function (name) {
      VIEWS[name].hidden = name !== state.view;
    });

    if (state.modal) {
      showModal(state.modal);
    } else {
      $('modal').hidden = true;
    }

    // Reset scroll only when the view actually changes. Closing a modal is also
    // an apply(), and resetting there would jump the accounts list back to the
    // top every time you dismissed a CD.
    if (state.view !== shownView) {
      var view = VIEWS[state.view];
      var scroller = view.querySelector('.scroll') || view.querySelector('.login');
      if (scroller) scroller.scrollTop = 0;
      shownView = state.view;
    }
  }

  /* Loading -------------------------------------------------------------
   * Forward navigation pauses on a spinner so the app feels like it's talking
   * to a server. Back deliberately doesn't -- real apps return instantly, and
   * delaying a popstate means the history entry has already changed while the
   * old screen is still showing.
   */

  var busy = false;

  function loader(on) { $('loader').hidden = !on; }

  function afterDelay(ms, done) {
    if (busy) return;          // ignore taps while a spinner is up
    busy = true;
    loader(true);
    setTimeout(function () {
      loader(false);
      busy = false;
      done();
    }, ms);
  }

  // Long enough to register as loading, short enough not to be annoying.
  function screenDelay() { return 350 + Math.random() * 450; }

  function navigate(view) {
    afterDelay(screenDelay(), function () {
      var state = { view: view, modal: null };
      history.pushState(state, '');
      apply(state);
    });
  }

  function replace(view) {
    var state = { view: view, modal: null };
    history.replaceState(state, '');
    apply(state);
  }

  function currentView() {
    return (history.state && history.state.view) || 'login';
  }

  window.addEventListener('popstate', function (event) {
    apply(event.state || { view: 'login', modal: null });
  });

  /* Modal ----------------------------------------------------------------
   * Stored in history state as a small spec rather than rendered HTML, so it
   * survives serialization and rebuilds identically on a back/forward.
   */

  function modalContent(spec) {
    if (spec.kind === 'transfer') {
      return {
        title: 'Transfer Scheduled',
        body: '<strong>' + spec.amount + '</strong> from ' + spec.from
          + ' to ' + spec.to + '. Funds are typically available in '
          + '1&ndash;3 business days.'
      };
    }

    if (spec.kind === 'deposit') {
      return {
        title: 'Deposit Submitted',
        body: '<strong>' + spec.amount + '</strong> to ' + spec.to
          + '. Funds are typically available the next business day. Keep the '
          + 'check until the deposit has posted.'
      };
    }

    // A CD. Everything shown comes from config.js, keyed by account id -- the
    // spec only carries the id so it stays serializable for history state.
    var account = accountById(spec.id);
    if (!account) {
      return {
        title: 'Account Details Unavailable',
        body: 'For details on this account, please call us at <strong>'
          + CFG.supportPhone + '</strong>.'
      };
    }

    function row(label, value) {
      return '<div class="deets__row"><span>' + label
        + '</span><strong>' + value + '</strong></div>';
    }

    return {
      title: account.name + ' ••••' + account.mask,
      body: '<div class="deets">'
        + row('Current APY', account.apy + '%')
        + row('Interest Rate', account.rate + '%')
        + row('Maturity Date', longDate(account.maturity))
        + '</div>'
        + '<p class="deets__note">Questions about this account? Call us at '
        + CFG.supportPhone + '.</p>'
    };
  }

  function accountById(id) {
    return CFG.accounts.filter(function (a) { return a.id === id; })[0];
  }

  function showModal(spec) {
    var content = modalContent(spec);
    $('modal-title').textContent = content.title;
    // Only ever our own strings from config, plus figures we formatted
    // ourselves. No transaction data reaches here.
    $('modal-body').innerHTML = content.body;
    $('modal').hidden = false;
  }

  function openModal(spec) {
    var state = { view: currentView(), modal: spec };
    history.pushState(state, '');
    apply(state);
  }

  // Going back is what actually closes it, so the Close button, a backdrop tap
  // and the back gesture all take the same path.
  function closeModal() { history.back(); }

  /* Login ---------------------------------------------------------------- */

  function wireLogin() {
    var form = $('login-form');
    var user = $('login-user');
    var pass = $('login-pass');
    var remember = $('login-remember');
    var banner = $('login-error');

    var saved = localStorage.getItem(STORE_USER);
    if (saved) {
      user.value = saved;
      remember.checked = true;
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();

      var ok = user.value.trim() === CFG.credentials.userId
        && pass.value === CFG.credentials.password;

      if (!ok) {
        banner.textContent = 'The information entered does not match our records. Please try again.';
        banner.hidden = false;
        pass.value = '';
        pass.focus();
        return;
      }

      banner.hidden = true;
      pass.value = '';

      if (remember.checked) {
        localStorage.setItem(STORE_USER, user.value.trim());
      } else {
        localStorage.removeItem(STORE_USER);
      }

      localStorage.setItem(STORE_SESSION, '1');

      // Replace rather than push: backing into a login form you've already
      // cleared is not something a real app does. Authenticating gets a longer
      // beat than a plain screen change, which is how it actually feels.
      afterDelay(700 + Math.random() * 600, function () {
        replace('accounts');
      });
    });

    $('log-out').addEventListener('click', function () {
      localStorage.removeItem(STORE_SESSION);
      pass.value = '';
      banner.hidden = true;
      var remembered = localStorage.getItem(STORE_USER);
      user.value = remembered || '';
      remember.checked = !!remembered;
      replace('login');
    });
  }

  /* Biometric sign-in -----------------------------------------------------
   * Real WebAuthn against the device's platform authenticator, so tapping the
   * button raises the actual Android fingerprint sheet -- not a mock overlay.
   *
   * There's no server here, so nothing verifies the returned signature. What
   * this genuinely gives you is the OS refusing to resolve the promise until
   * your fingerprint matches. That's a real biometric gate on opening the app,
   * and it is NOT authentication in the cryptographic sense. Same caveat as the
   * password: this is a UI state machine.
   *
   * Requires a secure context, which localhost and HTTPS both satisfy.
   */

  var STORE_CRED = 'ds.credentialId';

  function toBase64(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  function fromBase64(text) {
    var binary = atob(text);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function randomBytes(length) {
    var bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return bytes;
  }

  function biometricSupported() {
    if (!window.PublicKeyCredential
        || !navigator.credentials
        || !PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) {
      return Promise.resolve(false);
    }
    return PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
      .catch(function () { return false; });
  }

  function enrolled() { return !!localStorage.getItem(STORE_CRED); }

  // rp.id is deliberately omitted so the browser derives it from the current
  // origin. Hardcoding it would break the moment this moved between localhost
  // and the Pages domain.
  function enrol(userId) {
    return navigator.credentials.create({
      publicKey: {
        challenge: randomBytes(32),
        rp: { name: CFG.bankName },
        user: {
          id: randomBytes(16),
          name: userId,
          displayName: userId
        },
        pubKeyCredParams: [
          { type: 'public-key', alg: -7 },    // ES256
          { type: 'public-key', alg: -257 }   // RS256
        ],
        authenticatorSelection: {
          authenticatorAttachment: 'platform',
          userVerification: 'required',
          residentKey: 'preferred'
        },
        timeout: 60000,
        attestation: 'none'
      }
    }).then(function (credential) {
      localStorage.setItem(STORE_CRED, toBase64(credential.rawId));
      return credential;
    });
  }

  function verify() {
    return navigator.credentials.get({
      publicKey: {
        challenge: randomBytes(32),
        allowCredentials: [{
          type: 'public-key',
          id: fromBase64(localStorage.getItem(STORE_CRED)),
          transports: ['internal']
        }],
        userVerification: 'required',
        timeout: 60000
      }
    });
  }

  function wireBiometrics() {
    var button = $('bio-login');
    var label = $('bio-label');
    var banner = $('login-error');
    var user = $('login-user');
    var pass = $('login-pass');

    function refresh() {
      label.textContent = enrolled()
        ? 'Sign in with fingerprint'
        : 'Set up fingerprint sign-in';
    }

    biometricSupported().then(function (available) {
      if (!available) return;   // no fingerprint hardware: leave it hidden
      refresh();
      button.hidden = false;
    });

    function signedIn() {
      localStorage.setItem(STORE_SESSION, '1');
      pass.value = '';
      banner.hidden = true;
      afterDelay(700 + Math.random() * 600, function () { replace('accounts'); });
    }

    function failed(error) {
      // A cancelled prompt throws NotAllowedError, which isn't worth alarming
      // wording -- the user just backed out.
      var cancelled = error && (error.name === 'NotAllowedError'
        || error.name === 'AbortError');
      banner.textContent = cancelled
        ? 'Fingerprint sign-in was cancelled.'
        : 'Fingerprint sign-in isn’t available right now. Use your password.';
      banner.hidden = false;
      refresh();
    }

    // The OS prompt is up while the promise is unresolved, and busy only covers
    // the spinner. Without this a second tap starts a concurrent WebAuthn
    // request, which the browser rejects and which would surface as a spurious
    // error on the first one.
    var pending = false;

    function settle(handler) {
      return function (arg) {
        pending = false;
        handler(arg);
      };
    }

    button.addEventListener('click', function () {
      if (busy || pending) return;
      banner.hidden = true;

      if (enrolled()) {
        pending = true;
        verify().then(settle(signedIn)).catch(settle(failed));
        return;
      }

      // First run: prove who you are with the password once, then enrol. Letting
      // any passing fingerprint set itself up as a login would be worse than the
      // password alone.
      var ok = user.value.trim() === CFG.credentials.userId
        && pass.value === CFG.credentials.password;
      if (!ok) {
        banner.textContent = 'Enter your User ID and password once to enable '
          + 'fingerprint sign-in.';
        banner.hidden = false;
        return;
      }

      pending = true;
      enrol(user.value.trim()).then(settle(function () {
        refresh();
        signedIn();
      })).catch(settle(failed));
    });
  }

  /* Accounts ------------------------------------------------------------- */

  function renderAccounts() {
    var list = $('account-rows');
    var total = 0;

    list.innerHTML = '';

    CFG.accounts.forEach(function (account) {
      total += cents(account.balance);

      var item = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'row';

      var main = document.createElement('div');
      main.className = 'row__main';

      var name = document.createElement('div');
      name.className = 'row__name';
      name.textContent = account.name;

      var mask = document.createElement('div');
      mask.className = 'row__mask';
      mask.textContent = '••••' + account.mask;

      main.appendChild(name);
      main.appendChild(mask);

      var amount = document.createElement('div');
      amount.className = 'row__amount';
      amount.textContent = money(cents(account.balance));

      button.appendChild(main);
      button.appendChild(amount);
      button.insertAdjacentHTML('beforeend',
        '<svg class="row__chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>');

      button.addEventListener('click', function () {
        if (account.kind === 'savings') {
          navigate('transactions');
        } else {
          openModal({ kind: 'cd', id: account.id });
        }
      });

      item.appendChild(button);
      list.appendChild(item);
    });

    // Summed from the account list, never hardcoded -- change a balance in
    // config.js and this follows.
    $('total-balance').textContent = money(total);

    var savings = savingsAccount();
    if (savings) {
      $('savings-balance').textContent = money(cents(savings.balance));
      // Just the mask -- the header bar already says "Online Savings".
      $('savings-mask').textContent = '••••' + savings.mask;
    }
  }

  function savingsAccount() {
    return CFG.accounts.filter(function (a) { return a.kind === 'savings'; })[0];
  }

  /* Transfer ------------------------------------------------------------- */

  function option(text, value) {
    var node = document.createElement('option');
    node.textContent = text;
    node.value = value;
    return node;
  }

  function fillTransfer() {
    var from = $('tf-from');
    var to = $('tf-to');

    from.innerHTML = '';
    to.innerHTML = '';

    // Names only, no masked account numbers -- on this screen they're noise.
    //
    // From: linked outside accounts. The first is selected by default, which is
    // how Chase ends up preselected.
    CFG.externalAccounts.forEach(function (account) {
      from.appendChild(option(account.name, account.id));
    });

    // To: savings only. You can't pay into a CD mid-term, so nothing else
    // belongs in this list.
    CFG.accounts.forEach(function (account) {
      if (account.kind === 'savings') {
        to.appendChild(option(account.name, account.id));
      }
    });
  }

  // Returns cents, or null when the text isn't a usable amount.
  function parseAmount(text) {
    var clean = String(text).replace(/[$,\s]/g, '');
    if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
    var value = cents(clean);
    return value > 0 ? value : null;
  }

  function wireTransfer() {
    var form = $('transfer-form');
    var amount = $('tf-amount');
    var banner = $('transfer-error');

    $('open-transfer').addEventListener('click', function () {
      banner.hidden = true;
      amount.value = '';
      navigate('transfer');
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();

      var value = parseAmount(amount.value);
      if (value === null) {
        banner.textContent = 'Enter a transfer amount greater than $0.00.';
        banner.hidden = false;
        amount.focus();
        return;
      }

      var from = $('tf-from');
      var to = $('tf-to');

      banner.hidden = true;

      var spec = {
        kind: 'transfer',
        amount: money(value),
        from: from.options[from.selectedIndex].textContent,
        to: to.options[to.selectedIndex].textContent
      };

      // Random 2-5 seconds on the spinner. Submitting a transfer is the one
      // place a bank app genuinely makes you wait, so this is where the delay
      // buys the most realism.
      afterDelay(2000 + Math.random() * 3000, function () {
        amount.value = '';
        // Nothing moves -- and a real ACH transfer wouldn't post today either,
        // so "scheduled" is both honest and what the app would actually say.
        openModal(spec);
      });
    });
  }

  /* Deposit a check -------------------------------------------------------
   * The camera comes from <input type="file" capture="environment">, which on
   * Android opens the rear camera straight away. getUserMedia with a live
   * viewfinder would be the alternative, but it needs a permission prompt and a
   * lot more code for a worse result -- the system camera app has focus,
   * exposure and a shutter already.
   */

  // Object URLs for the two captures, so they can be revoked on replacement.
  var shots = { front: null, back: null };

  function fillDeposit() {
    var to = $('dp-to');
    to.innerHTML = '';
    CFG.accounts.forEach(function (account) {
      if (account.kind === 'savings') {
        to.appendChild(option(account.name, account.id));
      }
    });
  }

  function clearShot(side) {
    if (shots[side]) {
      URL.revokeObjectURL(shots[side]);
      shots[side] = null;
    }
    var input = $('dp-' + side);
    var thumb = $('dp-' + side + '-thumb');
    var tile = input.closest('.shot');

    input.value = '';
    thumb.hidden = true;
    thumb.removeAttribute('src');
    tile.classList.remove('is-set');
    tile.querySelector('.shot__done').hidden = true;
  }

  function resetDeposit() {
    $('deposit-error').hidden = true;
    $('dp-amount').value = '';
    clearShot('front');
    clearShot('back');
  }

  function wireShot(side) {
    var input = $('dp-' + side);
    var thumb = $('dp-' + side + '-thumb');
    var tile = input.closest('.shot');

    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;

      // Revoke the previous URL before replacing it, or each retake leaks the
      // last photo for the lifetime of the page.
      if (shots[side]) URL.revokeObjectURL(shots[side]);
      shots[side] = URL.createObjectURL(file);

      thumb.src = shots[side];
      thumb.hidden = false;
      tile.classList.add('is-set');
      tile.querySelector('.shot__done').hidden = false;
      $('deposit-error').hidden = true;
    });
  }

  function wireDeposit() {
    var form = $('deposit-form');
    var amount = $('dp-amount');
    var banner = $('deposit-error');

    $('open-deposit').addEventListener('click', function () {
      resetDeposit();
      navigate('deposit');
    });

    wireShot('front');
    wireShot('back');

    form.addEventListener('submit', function (event) {
      event.preventDefault();

      function fail(message) {
        banner.textContent = message;
        banner.hidden = false;
      }

      var value = parseAmount(amount.value);
      if (value === null) {
        fail('Enter a deposit amount greater than $0.00.');
        amount.focus();
        return;
      }
      if (!shots.front) { fail('Take a photo of the front of your check.'); return; }
      if (!shots.back) { fail('Take a photo of the back of your check.'); return; }

      var to = $('dp-to');
      var spec = {
        kind: 'deposit',
        amount: money(value),
        to: to.options[to.selectedIndex].textContent
      };

      banner.hidden = true;

      // Same random 2-5s as a transfer. Nothing is uploaded and no balance
      // moves; a real check deposit wouldn't post today either.
      afterDelay(2000 + Math.random() * 3000, function () {
        resetDeposit();
        openModal(spec);
      });
    });
  }

  /* Transactions --------------------------------------------------------- */

  var filter = 'all';
  var query = '';

  function visible() {
    var needle = query.trim().toLowerCase();

    return TX.filter(function (row) {
      var amount = cents(row.amount);
      if (filter === 'in' && amount <= 0) return false;
      if (filter === 'out' && amount >= 0) return false;
      if (needle && row.description.toLowerCase().indexOf(needle) === -1) return false;
      return true;
    });
  }

  function renderTransactions() {
    var rows = visible();
    var host = $('tx-list');
    var fragment = document.createDocumentFragment();
    var month = null;

    host.innerHTML = '';

    rows.forEach(function (row) {
      var heading = monthLabel(row.date);
      if (heading !== month) {
        month = heading;
        var bar = document.createElement('div');
        bar.className = 'month';
        bar.textContent = heading;
        fragment.appendChild(bar);
      }

      var amount = cents(row.amount);
      var credit = amount > 0;

      var item = document.createElement('div');
      item.className = 'tx';

      var main = document.createElement('div');
      main.className = 'tx__main';

      var desc = document.createElement('div');
      desc.className = 'tx__desc';
      desc.textContent = row.description;

      var date = document.createElement('div');
      date.className = 'tx__date';
      date.textContent = usDate(row.date);

      main.appendChild(desc);
      main.appendChild(date);

      var right = document.createElement('div');
      right.className = 'tx__right';

      var value = document.createElement('div');
      value.className = 'tx__amount' + (credit ? ' is-credit' : '');
      // U+2212 minus, not a hyphen -- it aligns with digits at this weight.
      value.textContent = (credit ? '+' : '−') + money(amount);

      var balance = document.createElement('div');
      balance.className = 'tx__bal';
      balance.textContent = money(cents(row.balance));

      right.appendChild(value);
      right.appendChild(balance);

      item.appendChild(main);
      item.appendChild(right);
      fragment.appendChild(item);
    });

    host.appendChild(fragment);
    $('tx-empty').hidden = rows.length > 0;
  }

  function wireTransactions() {
    $('tx-search').addEventListener('input', function (event) {
      query = event.target.value;
      renderTransactions();
    });

    document.querySelectorAll('.seg').forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('.seg').forEach(function (other) {
          other.classList.toggle('is-on', other === button);
        });
        filter = button.dataset.filter;
        renderTransactions();
      });
    });
  }

  /* Global wiring -------------------------------------------------------- */

  function wireGlobal() {
    $('open-alerts').addEventListener('click', function () { navigate('alerts'); });

    document.querySelectorAll('[data-back]').forEach(function (button) {
      button.addEventListener('click', function () { history.back(); });
    });

    document.querySelectorAll('[data-close-modal]').forEach(function (node) {
      node.addEventListener('click', closeModal);
    });

    // Controls that are deliberately inert: the two login links and Deposit
    // Check. They do nothing at all, silently -- no message, no
    // acknowledgement. preventDefault is only here to stop the href="#" links
    // jumping the page to the top.
    document.addEventListener('click', function (event) {
      if (event.target.closest('[data-inert]')) event.preventDefault();
    });
  }

  /* Boot ----------------------------------------------------------------- */

  fillTemplates();
  initTheme();
  renderAccounts();
  fillTransfer();
  fillDeposit();
  renderTransactions();
  wireLogin();
  wireBiometrics();
  wireTransfer();
  wireDeposit();
  wireTransactions();
  wireGlobal();

  replace(localStorage.getItem(STORE_SESSION) ? 'accounts' : 'login');

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').catch(function () {
        // Offline support is a nice-to-have; a failure here shouldn't break
        // the app when it's running from a plain file server.
      });
    });
  }
})();
