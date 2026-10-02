# -*- coding: utf-8 -*-
"""A from-scratch, standalone FIFO cost-of-goods-sold (COGS) engine.

This is a clean-room demo written to show the pattern, not extracted from
any employer/client codebase - no real company data, no real item codes.

The problem: given a stream of purchase ("in") and sale ("out") events for
an item, reconstruct the cost of each sale under First-In-First-Out
accounting - the oldest unsold unit's cost is used first - and detect the
situation every FIFO engine eventually has to handle: a sale that outruns
the inventory layers currently on hand.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Literal


@dataclass
class Layer:
    """One inventory layer: a batch of units bought at a single unit cost."""
    qty: Decimal
    unit_cost: Decimal


@dataclass
class Movement:
    """One inventory event, in chronological order."""
    kind: Literal["in", "out"]
    qty: Decimal
    unit_cost: Decimal | None = None  # required for "in", ignored for "out"
    ref: str = ""                     # document reference, for the audit trail


@dataclass
class ConsumedLayer:
    """One FIFO layer (or part of one) consumed by a single sale."""
    qty: Decimal
    unit_cost: Decimal
    layer_origin_ref: str


@dataclass
class SaleResult:
    ref: str
    qty_requested: Decimal
    qty_fulfilled: Decimal
    cogs: Decimal
    consumed: list[ConsumedLayer] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        """True when inventory ran out mid-sale - the case that matters."""
        return self.qty_fulfilled < self.qty_requested

    @property
    def shortage_qty(self) -> Decimal:
        return self.qty_requested - self.qty_fulfilled


class InsufficientStockError(Exception):
    """Raised in strict mode when a sale can't be fully covered by stock on hand."""

    def __init__(self, result: SaleResult):
        super().__init__(
            f"{result.ref}: requested {result.qty_requested}, "
            f"only {result.qty_fulfilled} available "
            f"(short by {result.shortage_qty})"
        )
        self.result = result


class FifoCogsEngine:
    """
    Replays a chronological stream of movements and computes COGS per sale
    under FIFO. Deliberately explicit about the one case a lot of naive
    implementations get wrong: what happens when a sale is bigger than
    the stock actually on hand.

    strict=True (default): raises InsufficientStockError rather than
    silently going negative - a FIFO engine that quietly invents cost from
    layers that don't exist produces numbers nobody can trust.

    strict=False: fulfills what it can from real layers and reports the
    unfulfilled remainder via SaleResult.shortage_qty, so a caller that
    wants to handle backorders/negative stock explicitly still can.
    """

    def __init__(self, strict: bool = True):
        self.strict = strict
        self._layers: deque[tuple[Layer, str]] = deque()

    def replay(self, movements: Iterable[Movement]) -> list[SaleResult]:
        results: list[SaleResult] = []
        for m in movements:
            if m.kind == "in":
                if m.unit_cost is None:
                    raise ValueError(f"{m.ref}: an 'in' movement requires unit_cost")
                self._layers.append((Layer(qty=m.qty, unit_cost=m.unit_cost), m.ref))
            elif m.kind == "out":
                results.append(self._consume(m))
            else:
                raise ValueError(f"unknown movement kind: {m.kind!r}")
        return results

    def _consume(self, m: Movement) -> SaleResult:
        remaining = m.qty
        consumed: list[ConsumedLayer] = []
        cogs = Decimal("0")

        while remaining > 0 and self._layers:
            layer, origin_ref = self._layers[0]
            take = min(layer.qty, remaining)

            cogs += take * layer.unit_cost
            consumed.append(ConsumedLayer(qty=take, unit_cost=layer.unit_cost,
                                           layer_origin_ref=origin_ref))
            layer.qty -= take
            remaining -= take

            if layer.qty == 0:
                self._layers.popleft()

        fulfilled = m.qty - remaining
        result = SaleResult(
            ref=m.ref,
            qty_requested=m.qty,
            qty_fulfilled=fulfilled,
            cogs=cogs,
            consumed=consumed,
        )

        if self.strict and result.is_short:
            raise InsufficientStockError(result)

        return result

    @property
    def remaining_layers(self) -> list[Layer]:
        """What's still on hand after replay - useful for a closing-stock check."""
        return [layer for layer, _ref in self._layers]

    @property
    def remaining_value(self) -> Decimal:
        return sum((layer.qty * layer.unit_cost for layer in self.remaining_layers),
                   Decimal("0"))
