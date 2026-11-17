"""Regression test for docs/trace_case.md: seeded_regression C-014@11 (FM-05 pre_deducted).

First wrong step: event #5 `proposal` 120000 (quote 150000 minus the 30000 already refunded on O-515);
the host then subtracts the 30000 again, so the ledger holds 90000 instead of 120000 while the reply
still says 120.000đ. The same trial on `fixed` must pass every assertion below.
"""
import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="trace_case", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return {shape: investigate(shape, "C-014", 11) for shape in ("seeded_regression", "fixed")}


def test_first_wrong_step_is_the_pre_deducted_proposal(cases):
    events = cases["seeded_regression"]["trial"]["events"]
    kinds = [e["kind"] for e in events]
    assert kinds[:5] == ["handoff", "investigator", "quote", "refund_history", "proposal"]
    assert events[2]["payload"]["amount_vnd"] == 150000          # #3 quote is right (max of clauses)
    assert events[3]["payload"]["refunded_vnd"] == 30000         # #4 read-only lookup is right
    assert events[4]["payload"]["amount_vnd"] == 120000          # #5 the agent deducts before the host
    assert "proposal" not in [e["kind"] for e in cases["fixed"]["trial"]["events"]]


@pytest.mark.parametrize("shape,ok", [("seeded_regression", False), ("fixed", True)])
def test_graders_catch_c014_regression(cases, shape, ok):
    from lab9 import graders

    trial, label = cases[shape]["trial"], cases[shape]["label"]
    assert graders.RefundAmountCorrect().evaluate(_ctx(trial, label)).value is ok      # ledger 90000 vs 120000
    assert graders.ProposalAmountCorrect().evaluate(_ctx(trial, label)).value is ok    # proposal 120000 vs 150000
    assert graders.ReplyMatchesLedger().evaluate(_ctx(trial, label)).value is ok       # reply 120000 vs ledger 90000
    assert trial["lab8_pass"] is ok
