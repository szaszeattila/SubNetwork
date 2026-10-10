# Security

## Reporting a problem

Please report a security problem privately, through GitHub's **Report a
vulnerability** button under this repository's **Security** tab, and not in a
public issue. This is a one-person project, so a reply may take some days.
Once a fix is published, the report can be made public, with credit if you
want it.

A wrong value in the data, such as a mislabelled mechanism or a bad
measurement, is not a security problem: please open an ordinary issue for it.

## What is in scope

The viewer is one static page with no server side, no accounts, no cookies and
no form that sends anything anywhere. What can go wrong is therefore mostly on
the page itself:

- **Text from the data reaching the page as markup.** Paper titles, protein
  names and synonyms come from public databases and are written into the page.
  Everything is meant to be escaped first (rule 11 of the invariants in
  [CLAUDE.md](CLAUDE.md)). A record that runs as script or breaks the layout is
  a bug worth reporting.
- **The page's Content-Security-Policy**, which allows only the page's own
  files and its one inline script, by hash (`scripts/csp.py`). A way around it
  is in scope.
- **The link a page address makes** (`#m=CHEMBL113&tier=…`). Only a lookup
  key is read from it. Anything that makes it do more is in scope.
- **The pipeline scripts**, where they read downloaded files. A crafted
  upstream file that makes a script write outside the repository or run code
  is in scope.

Out of scope: the hosting provider's own infrastructure, denial of service, and
anything that needs a compromised machine or browser to begin with.
