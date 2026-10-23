# Contributing

Issues and pull requests are welcome. Please keep the prototype read-only and preserve human approval boundaries.

1. Open an issue describing the business case and evidence ID before proposing a new rule.
2. Add a focused test for a new failure mode or changed behavior.
3. Run `PYTHONPATH=src python -m unittest discover -s tests -v`.
4. Describe any change to the input or output format in `docs/api.md` and add a changelog entry.

Do not commit real procurement records, quotes, credentials, identifiable staff data, or restricted chemical documentation. Use fabricated fixtures.
