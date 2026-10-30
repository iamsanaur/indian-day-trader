# Security

## Reporting

Please report vulnerabilities privately via GitHub's **Report a vulnerability** (Security tab),
not in public issues.

## Your credentials

- Dhan credentials are read only from `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN` environment variables
  and are never written to disk by this project.
- The `idt/` workspace (config, plans, orders, journal) is git-ignored. Don't commit it.
- Never paste tokens into issues, PRs or chat logs. Dhan tokens can be revoked from web.dhan.co.

## Scope

This project performs **read-only** market-data calls. It contains no order-placement code.
