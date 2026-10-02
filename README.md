# fifo-cogs-engine-demo

> **Demo reconstruction of a real production system.** The original
> reconstructs cost-of-goods from inventory layers and reconciles it
> against the accounting journal; it was built for **GSI Group**
> (Semarang, Indonesia) as part of their Accurate Online → BigQuery data
> work. That system's code, item catalogue and financial data belong to
> the company and are **not** published here - this repository is a
> clean-room rebuild of the algorithm and its failure handling, on
> synthetic data only.



A standalone First-In-First-Out (FIFO) cost-of-goods-sold engine, written
as a clean-room demo of the pattern — no real company data, no real item
codes, nothing copied from any employer/client codebase.

## The problem

Given a chronological stream of purchases ("in" — qty + unit cost) and
sales ("out" — qty only), reconstruct what each sale actually cost under
FIFO accounting: the **oldest unsold unit's cost is used first**, and a
sale that spans two purchase batches has to be split and costed per-layer,
not averaged.

```python
from decimal import Decimal
from fifo_cogs import FifoCogsEngine, Movement

engine = FifoCogsEngine()
results = engine.replay([
    Movement("in",  qty=Decimal(5), unit_cost=Decimal("10.00"), ref="PO-1"),
    Movement("in",  qty=Decimal(5), unit_cost=Decimal("12.00"), ref="PO-2"),
    Movement("out", qty=Decimal(8), ref="SO-1"),
])
print(results[0].cogs)  # 86.00 -> 5 units @ 10.00 + 3 units @ 12.00
```

## The part that actually matters: what happens when stock runs out mid-sale

A sale bigger than what's physically on hand is the case a lot of naive
FIFO implementations quietly get wrong — either by going negative and
inventing cost from a layer that doesn't exist, or by crashing with no
useful information about *how much* was actually fulfillable.

This engine makes that an explicit, tested decision:

- **`strict=True` (default):** raises `InsufficientStockError`, carrying
  exactly how much *was* fulfilled and the shortage amount — so a caller
  can decide what to do (block the sale, flag it for review, etc.)
  instead of silently producing a wrong number.
- **`strict=False`:** fulfills what it can from real inventory layers and
  reports the shortfall via `SaleResult.is_short` /
  `SaleResult.shortage_qty`, for callers that want to handle
  backorders/negative stock explicitly rather than block on it.

## Run the tests

```bash
pip install pytest
python -m pytest tests/ -v
```

8 tests, covering: multi-layer sales at different unit costs, exact-layer
boundary consumption (a classic off-by-one where the depleted layer
doesn't get removed), both shortage modes, and input validation.

## Why this shape

In a real system I built, this same pattern reconstructs cost-of-goods
for every sale from inventory layers, and I validated the output against
the company's accounting journal as the ground-truth referee rather than
trusting the engine's own output: **963 of 963 documents matched**. That
validation step — checking against an independent source of truth instead
of just "the code runs and the number looks plausible" — is the part of
this pattern I think is actually worth demonstrating, more than the FIFO
algorithm itself (which is well-known).

## License

MIT.
