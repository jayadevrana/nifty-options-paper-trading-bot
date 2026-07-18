# NIFTY Option Selling Paper Trader

Paper-trading web app for a defined-risk NIFTY option-selling strategy named `my first strategy with claude`.

The app:

- uses free public NSE website endpoints for live market snapshots
- trades only NIFTY options in paper mode
- sizes positions from a `Rs. 10,00,000` capital base
- applies hedges, daily loss limits, drawdown controls, and time-based exits
- deducts Zerodha-style round-trip charges on every closed paper trade
- stores trades, equity, and drawdown locally in SQLite

## Strategy

The live paper strategy is a single-entry intraday hedged short strangle expressed as a defined-risk iron condor:

- waits for the first 15 minutes of market data
- enters only once per day between `09:35` and `10:15` IST
- sells an OTM call and OTM put around the opening range
- buys wings `100` points away on both sides to cap risk
- exits on profit target, stop-loss, short-strike breach, or at `15:15` IST

Risk guardrails:

- capital base: `Rs. 10,00,000`
- max risk per trade: `1.25%`
- max daily loss: `2.5%`
- soft overall drawdown cutoff: `8%`
- one active position at a time

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Notes

- This is a paper-trading system only. It does not place live broker orders.
- The NSE feed path is free but unofficial for automation and may rate-limit or change. The app retries and keeps the last good snapshot.
- Paper trading is configured to start on `2026-03-26` by default.
- Zerodha costs are modeled from public pricing and support documentation. Exact live-broker debits can differ slightly.
- Trading automation is infrastructure, not financial advice. No profit guarantees. Test in dry-run/paper before live.

## Author

Built by [Jayadev Rana](https://jayadevrana.in) — @bluealgocapital · [YouTube](https://www.youtube.com/@jayadevrana3657) · [GitHub](https://github.com/jayadevrana)
