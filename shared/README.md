# Shared by every implementation

The PHP, Node and Python servers all read these files, so a change here reaches all three.

- `schema.sql`: the SQLite schema, applied on every connection.
- `cards.json`: the test cards, in the order the hosted page lists them. `first` is what paying on the hosted page does (`pay`, `decline` or `3ds`), `later` what a charge on the saved card does (`pay` or `decline`). `expired` gives the card an expiry date in the past.
- `templates/`: the HTML of the hosted page and the dashboard. `{{name}}` inserts a value HTML-escaped, `{{{name}}}` inserts it as it is. There is no other template syntax: the servers decide what to show and pass plain values, such as `hidden` for an element that should not appear.
