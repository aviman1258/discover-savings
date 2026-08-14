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
  //
  // The savings balance must match cell D2 of the spreadsheet -- that's the
  // anchor every running balance is computed from. tools/import_ledger.py
  // refuses to run if they disagree.
  //
  // CD 3364 was removed when it matured on 2026-08-04 and its balance moved
  // into savings. The ledger still shows that transfer, plus CD 1212 opening
  // and CD 0127 maturing earlier -- all referring to accounts that no longer
  // exist, which is correct for closed CDs.
  // apy / rate are percentages without the sign; maturity is ISO so the app
  // formats it and there's no date string to get wrong in two places.
  accounts: [
    { id: 'savings', kind: 'savings', name: 'Online Savings',         mask: '4417', balance: '52303.84' },
    { id: 'cd-2093', kind: 'cd',      name: 'Certificate of Deposit', mask: '2093', balance: '28226.90',
      apy: '3.90', rate: '3.83', maturity: '2027-04-11' },
    { id: 'cd-7715', kind: 'cd',      name: 'Certificate of Deposit', mask: '7715', balance: '21798.31',
      apy: '3.90', rate: '3.83', maturity: '2027-04-30' }
  ],

  // Linked outside accounts, used as the "From" options on the transfer screen.
  // JPMorgan Chase is where the ACH deposits in the ledger come from. The mask
  // is a placeholder -- the transaction descriptions don't carry one, so set it
  // to the real last four if you want it to match your statements.
  externalAccounts: [
    { id: 'chase', name: 'JPMorgan Chase Checking', mask: '1182' }
  ]
};
