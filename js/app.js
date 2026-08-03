/* Discover-style savings app.
 *
 * Three views in one document, swapped by toggling [hidden]. A real page load
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

  /* Shared fragments ------------------------------------------------------- */

  function fillTemplates() {
    var wordmark = $('tpl-wordmark');
    var fdic = $('tpl-fdic');

    document.querySelectorAll('[data-wordmark]').forEach(function (host) {
      var node = wordmark.content.cloneNode(true);
      node.querySelector('.wordmark').classList.add('wordmark--' + host.dataset.wordmark);
      host.appendChild(node);
    });

    document.querySelectorAll('[data-fdic]').forEach(function (host) {
      host.appendChild(fdic.content.cloneNode(true));
    });

    document.querySelectorAll('[data-foot]').forEach(function (host) {
      host.textContent = CFG.bankName + ', Member FDIC';
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
    transactions: $('view-transactions')
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

  function navigate(view) {
    var state = { view: view, modal: null };
    history.pushState(state, '');
    apply(state);
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
    if (spec.kind === 'cd') {
      return {
        title: 'Account Details Unavailable',
        body: 'For details on this account, including term and maturity, please call us at <strong>'
          + CFG.supportPhone + '</strong>.'
      };
    }

    return {
      title: 'Earlier Transactions Unavailable',
      body: 'Online activity is available for the most recent ' + CFG.historyMonths
        + ' months. For transactions before <strong>' + usDate(oldestDate())
        + '</strong>, please call us at <strong>' + CFG.supportPhone + '</strong>.'
    };
  }

  function showModal(spec) {
    var content = modalContent(spec);
    $('modal-title').textContent = content.title;
    // Only ever our own strings from config -- no transaction data reaches here.
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

  function oldestDate() {
    return TX.length ? TX[TX.length - 1].date : '';
  }

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
      // cleared is not something a real app does.
      replace('accounts');
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
          openModal({ kind: 'cd' });
        }
      });

      item.appendChild(button);
      list.appendChild(item);
    });

    // Summed from the account list, never hardcoded -- change a balance in
    // config.js and this follows.
    $('total-balance').textContent = money(total);

    var savings = CFG.accounts.filter(function (a) { return a.kind === 'savings'; })[0];
    if (savings) {
      $('savings-balance').textContent = money(cents(savings.balance));
      // Just the mask -- the header bar already says "Online Savings".
      $('savings-mask').textContent = '••••' + savings.mask;
    }
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
      var label = monthLabel(row.date);
      if (label !== month) {
        month = label;
        var heading = document.createElement('div');
        heading.className = 'month';
        heading.textContent = label;
        fragment.appendChild(heading);
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

    // A narrowed list isn't the end of history, so don't offer to load more.
    var narrowed = filter !== 'all' || query.trim() !== '';
    $('tx-more').hidden = narrowed || rows.length === 0;
  }

  function wireTransactions() {
    $('tx-back').addEventListener('click', function () { history.back(); });

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

    $('load-earlier').addEventListener('click', function () {
      openModal({ kind: 'history' });
    });
  }

  /* Global wiring -------------------------------------------------------- */

  function wireGlobal() {
    document.querySelectorAll('[data-close-modal]').forEach(function (node) {
      node.addEventListener('click', closeModal);
    });

    // Controls that are deliberately inert: the bell, the gear, the two login
    // links, Transfer Money and Deposit Check. They do nothing at all, silently
    // -- no message, no acknowledgement. preventDefault is only here to stop the
    // href="#" links jumping the page to the top.
    document.addEventListener('click', function (event) {
      if (event.target.closest('[data-inert]')) event.preventDefault();
    });
  }

  /* Boot ----------------------------------------------------------------- */

  fillTemplates();
  renderAccounts();
  renderTransactions();
  wireLogin();
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
