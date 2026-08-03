// Everything you might want to change lives here.

window.CONFIG = {
  // Static credential check. This is a UI state machine, not security --
  // anyone who views source can read these.
  credentials: {
    userId: 'achandra',
    password: '200Free'
  },

  bankName: 'Discover Bank',

  // Shown in the CD and end-of-history modals. Rendered as plain text on
  // purpose, not a tel: link, so a stray tap can't place a real call.
  supportPhone: '1-800-347-7000',

  // Balances are strings and get parsed to integer cents before any math,
  // so floating point never touches the money. The accounts screen total is
  // the sum of these, never a hardcoded figure.
  accounts: [
    { id: 'savings', kind: 'savings', name: 'Online Savings',           mask: '4417', balance: '2698.85'  },
    { id: 'cd-2093', kind: 'cd',      name: 'Certificate of Deposit',   mask: '2093', balance: '28226.90' },
    { id: 'cd-7715', kind: 'cd',      name: 'Certificate of Deposit',   mask: '7715', balance: '21798.31' },
    { id: 'cd-3364', kind: 'cd',      name: 'Certificate of Deposit',   mask: '3364', balance: '41461.55' }
  ],

  // How far back the app claims to load. Only used in the modal copy; the
  // actual cutoff date is read from the oldest row in data.js.
  historyMonths: 12
};
