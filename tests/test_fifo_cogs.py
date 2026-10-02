# -*- coding: utf-8 -*-
from decimal import Decimal

import pytest

from fifo_cogs import FifoCogsEngine, InsufficientStockError, Movement


def test_single_layer_simple_sale():
    engine = FifoCogsEngine()
    [result] = engine.replay([
        Movement("in", qty=Decimal(10), unit_cost=Decimal("5.00"), ref="PO-1"),
        Movement("out", qty=Decimal(4), ref="SO-1"),
    ])
    assert result.qty_fulfilled == Decimal(4)
    assert result.cogs == Decimal("20.00")  # 4 units * 5.00
    assert engine.remaining_value == Decimal("30.00")  # 6 units left * 5.00


def test_sale_spans_two_layers_at_different_costs():
    # This is the actual point of FIFO: a sale that spans two purchase
    # batches must be costed using EACH layer's own unit cost, not an
    # average and not the latest price.
    engine = FifoCogsEngine()
    [result] = engine.replay([
        Movement("in", qty=Decimal(5), unit_cost=Decimal("10.00"), ref="PO-1"),
        Movement("in", qty=Decimal(5), unit_cost=Decimal("12.00"), ref="PO-2"),
        Movement("out", qty=Decimal(8), ref="SO-1"),
    ])
    # 5 units @ 10.00 + 3 units @ 12.00 = 50.00 + 36.00 = 86.00
    assert result.cogs == Decimal("86.00")
    assert result.qty_fulfilled == Decimal(8)
    assert len(result.consumed) == 2
    assert result.consumed[0].layer_origin_ref == "PO-1"
    assert result.consumed[1].layer_origin_ref == "PO-2"
    # 2 units left from PO-2 at 12.00
    assert engine.remaining_value == Decimal("24.00")


def test_strict_mode_raises_on_insufficient_stock():
    engine = FifoCogsEngine(strict=True)
    with pytest.raises(InsufficientStockError) as exc_info:
        engine.replay([
            Movement("in", qty=Decimal(3), unit_cost=Decimal("10.00"), ref="PO-1"),
            Movement("out", qty=Decimal(5), ref="SO-1"),
        ])
    assert exc_info.value.result.shortage_qty == Decimal(2)
    assert exc_info.value.result.qty_fulfilled == Decimal(3)


def test_non_strict_mode_reports_shortage_instead_of_raising():
    engine = FifoCogsEngine(strict=False)
    [result] = engine.replay([
        Movement("in", qty=Decimal(3), unit_cost=Decimal("10.00"), ref="PO-1"),
        Movement("out", qty=Decimal(5), ref="SO-1"),
    ])
    assert result.is_short
    assert result.qty_fulfilled == Decimal(3)
    assert result.cogs == Decimal("30.00")  # only the 3 units it could actually cost
    assert engine.remaining_value == Decimal("0")


def test_multiple_sales_consume_layers_in_order():
    engine = FifoCogsEngine()
    results = engine.replay([
        Movement("in", qty=Decimal(10), unit_cost=Decimal("4.00"), ref="PO-1"),
        Movement("out", qty=Decimal(6), ref="SO-1"),
        Movement("in", qty=Decimal(10), unit_cost=Decimal("6.00"), ref="PO-2"),
        Movement("out", qty=Decimal(8), ref="SO-2"),  # 4 left from PO-1 + 4 from PO-2
    ])
    assert results[0].cogs == Decimal("24.00")  # 6 * 4.00
    assert results[1].cogs == Decimal("40.00")  # 4*4.00 + 4*6.00 = 16 + 24
    assert engine.remaining_value == Decimal("36.00")  # 6 units left @ 6.00


def test_in_movement_without_unit_cost_raises():
    engine = FifoCogsEngine()
    with pytest.raises(ValueError):
        engine.replay([Movement("in", qty=Decimal(5), ref="PO-1")])


def test_unknown_movement_kind_raises():
    engine = FifoCogsEngine()
    with pytest.raises(ValueError):
        engine.replay([Movement("transfer", qty=Decimal(5), ref="X-1")])  # type: ignore[arg-type]


def test_exact_layer_boundary_pops_the_layer():
    # A sale that consumes a layer EXACTLY (not more, not less) must still
    # pop that layer so the next sale doesn't try to read a qty=0 layer.
    engine = FifoCogsEngine()
    results = engine.replay([
        Movement("in", qty=Decimal(5), unit_cost=Decimal("2.00"), ref="PO-1"),
        Movement("out", qty=Decimal(5), ref="SO-1"),
        Movement("in", qty=Decimal(3), unit_cost=Decimal("9.00"), ref="PO-2"),
        Movement("out", qty=Decimal(1), ref="SO-2"),
    ])
    assert results[1].cogs == Decimal("9.00")  # must come from PO-2, not a stale PO-1 layer
