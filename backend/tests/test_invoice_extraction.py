"""Reading invoices: the pattern extractor on three fixtures, and what we check afterwards."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
from conftest import fake_fetcher
from fastapi.testclient import TestClient
from invoice_fixtures import FRENCH_ONE_CONTAINER, FRENCH_TWO_CONTAINERS, USD_INVOICE
from pdfs import make_pdf, make_pdf_without_text
from sqlalchemy.orm import Session

from app.adapters.extraction.llm_extractor import LlmExtractor
from app.adapters.extraction.regex_extractor import RegexExtractor, last_amount
from app.domain.fx.service import FxService
from app.domain.invoices.checks import CAPPED_CONFIDENCE, arithmetic_holds, check
from app.domain.invoices.ports import (
    ExtractedLine,
    ExtractionContext,
    ExtractionFailed,
    ExtractionInput,
    ExtractorNotConfigured,
    FreightInvoice,
)
from app.domain.invoices.registry import get_extractors
from app.domain.models import CostScope, CostType, Organization

CONTAINER_A = uuid.uuid4()
CONTAINER_B = uuid.uuid4()
CONTEXT = ExtractionContext(
    base_currency="EUR",
    containers={"MSCU4821990": CONTAINER_A, "TGHU7245081": CONTAINER_B},
)


def read(lines: list[str], context: ExtractionContext = CONTEXT) -> FreightInvoice:
    return RegexExtractor().extract(
        ExtractionInput(make_pdf(lines), "application/pdf", "facture.pdf"), context
    )


# ---------------------------------------------------------------------------- the pattern extractor


def test_a_french_forwarder_invoice_is_read_in_full() -> None:
    invoice = read(FRENCH_ONE_CONTAINER)

    assert invoice.vendor == "TRANSITEX SAS"
    assert invoice.invoice_number == "FA-2026-0912"
    assert invoice.invoice_date == date(2026, 3, 12)
    assert invoice.currency == "EUR"
    assert invoice.total == "4596.00"
    assert invoice.vat == "766.00"
    assert invoice.container_numbers == ["MSCU4821990"]

    charges = {ln.cost_type: ln.amount for ln in invoice.lines}
    assert charges == {
        CostType.OCEAN_FREIGHT: "3000.00",
        CostType.THC: "275.00",
        CostType.CUSTOMS_BROKERAGE: "130.00",
        CostType.DRAYAGE: "425.00",
    }


def test_the_charge_is_the_rightmost_amount_on_the_line() -> None:
    """« THC 2 x 137,50  275,00 » is a charge of 275, not of 2 or of 137.50."""
    assert last_amount("THC destination Le Havre    2    137,50    275,00") == Decimal("275.00")
    assert last_amount("Fret maritime CNNGB / FRLEH   1   3 000,00   3 000,00") == Decimal("3000.00")
    assert last_amount("Ocean freight               4,200.00") == Decimal("4200.00")
    assert last_amount("Nothing numeric here") is None


def test_totals_and_vat_are_not_mistaken_for_charges() -> None:
    invoice = read(FRENCH_ONE_CONTAINER)
    descriptions = " ".join(ln.description for ln in invoice.lines).upper()
    assert "TOTAL" not in descriptions
    assert "TVA" not in descriptions


def test_an_invoice_naming_two_containers_attributes_each_line() -> None:
    invoice = read(FRENCH_TWO_CONTAINERS)
    assert set(invoice.container_numbers) == {"MSCU4821990", "TGHU7245081"}
    by_container = {(ln.cost_type, ln.container_number) for ln in invoice.lines}
    assert (CostType.THC, "MSCU4821990") in by_container
    assert (CostType.THC, "TGHU7245081") in by_container
    assert (CostType.DEMURRAGE, "MSCU4821990") in by_container
    assert (CostType.DRAYAGE, "TGHU7245081") in by_container


def test_a_scan_fails_with_a_reason_a_person_can_act_on() -> None:
    with pytest.raises(ExtractionFailed) as raised:
        RegexExtractor().extract(ExtractionInput(make_pdf_without_text(), "application/pdf"), CONTEXT)
    assert raised.value.code == "NO_TEXT_LAYER"
    assert "by hand" in raised.value.message


def test_a_photograph_is_refused_by_the_pattern_extractor() -> None:
    with pytest.raises(ExtractionFailed):
        RegexExtractor().extract(ExtractionInput(b"\xff\xd8\xff", "image/jpeg"), CONTEXT)


def test_broken_bytes_fail_cleanly() -> None:
    with pytest.raises(ExtractionFailed):
        RegexExtractor().extract(ExtractionInput(b"%PDF-1.4\nnot really", "application/pdf"), CONTEXT)


# ---------------------------------------------------------------------------- the checks


def test_arithmetic_that_holds_and_arithmetic_that_does_not() -> None:
    invoice = read(FRENCH_ONE_CONTAINER)
    holds, difference = arithmetic_holds(invoice)
    assert holds and difference == Decimal("0.00")

    invoice.lines.pop()  # the forwarder's drayage line goes missing
    holds, difference = arithmetic_holds(invoice)
    assert not holds
    assert difference == Decimal("-425.00")


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def fx() -> FxService:
    return FxService(fake_fetcher)


def test_a_missing_line_caps_the_confidence_and_says_which_way(db: Session, org: Organization) -> None:
    invoice = read(FRENCH_ONE_CONTAINER)
    invoice.confidence = 0.9
    invoice.lines.pop()

    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 12))
    assert checked.confidence == CAPPED_CONFIDENCE
    assert "missing or misread" in " ".join(checked.notes)


def test_every_line_is_charged_to_the_only_container_named(db: Session, org: Organization) -> None:
    invoice = read(FRENCH_ONE_CONTAINER)
    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 12))
    assert [ln.scope for ln in checked.lines] == [CostScope.CONTAINER] * 4
    assert {ln.target_id for ln in checked.lines} == {CONTAINER_A}


def test_a_container_we_do_not_have_is_dropped_and_said_out_loud(db: Session, org: Organization) -> None:
    """The model is handed the organization's containers; anything else it returns is not a target."""
    invoice = FreightInvoice(
        currency="EUR",
        lines=[
            ExtractedLine(
                description="THC",
                amount="275.00",
                cost_type=CostType.THC,
                container_number="ZZZU0000000",
                confidence=0.9,
            )
        ],
    )
    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 12))
    (line,) = checked.lines
    assert line.scope is None and line.target_id is None
    assert line.confidence <= CAPPED_CONFIDENCE
    assert "not one of this organization's containers" in " ".join(line.notes)


def test_a_currency_without_a_rate_marks_the_line_for_review(db: Session, org: Organization) -> None:
    invoice = read(USD_INVOICE)
    assert invoice.currency == "USD"
    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 5))
    assert checked.lines  # the charges were read
    for line in checked.lines:
        assert line.currency == "USD"
    # the fake fetcher knows USD, so nothing is flagged; an unknown currency is another story
    invoice.lines[0].currency = "SEK"
    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 5))
    assert "has to be entered by hand" in " ".join(checked.lines[0].notes)
    assert checked.lines[0].confidence <= CAPPED_CONFIDENCE


def test_several_containers_asks_for_a_second_look(db: Session, org: Organization) -> None:
    invoice = read(FRENCH_TWO_CONTAINERS)
    checked = check(db, fx(), invoice, CONTEXT, base_currency="EUR", invoice_date=date(2026, 3, 18))
    assert "several containers" in " ".join(checked.notes)
    targets = {ln.target_id for ln in checked.lines}
    assert targets == {CONTAINER_A, CONTAINER_B}


# ---------------------------------------------------------------------------- the model extractor


def test_the_model_extractor_says_which_key_is_missing() -> None:
    with pytest.raises(ExtractorNotConfigured) as raised:
        LlmExtractor(None, "claude-opus-5").extract(
            ExtractionInput(make_pdf(FRENCH_ONE_CONTAINER), "application/pdf"), CONTEXT
        )
    assert "EXTRACTION_API_KEY" in raised.value.message


def llm(handler) -> LlmExtractor:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.test")
    return LlmExtractor("sk-test", "claude-opus-5", api_url="https://api.test/v1/messages", client=client)


def test_the_model_is_given_the_containers_and_its_answer_is_validated() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["prompt"] = body["messages"][0]["content"]
        seen["api_key"] = request.headers["x-api-key"]
        answer = {
            "vendor": "TRANSITEX SAS",
            "invoice_number": "FA-2026-0912",
            "invoice_date": "2026-03-12",
            "currency": "EUR",
            "total": "4596.00",
            "vat": "766.00",
            "lines": [
                {
                    "description": "Fret maritime",
                    "amount": "3000.00",
                    "cost_type": "OCEAN_FREIGHT",
                    "container_number": "MSCU4821990",
                    "confidence": 0.95,
                }
            ],
            "container_numbers": ["MSCU4821990"],
            "confidence": 0.9,
        }
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(answer)}]})

    invoice = llm(handler).extract(
        ExtractionInput(make_pdf(FRENCH_ONE_CONTAINER), "application/pdf"), CONTEXT
    )
    assert "MSCU4821990" in str(seen["prompt"])  # it recognises references, it does not invent them
    assert seen["api_key"] == "sk-test"
    assert invoice.lines[0].amount == "3000.00"  # a string all the way to Decimal
    assert invoice.confidence == 0.9


def test_a_fenced_answer_is_still_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        text = '```json\n{"lines": [], "confidence": 0.4}\n```'
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})

    assert (
        llm(handler)
        .extract(ExtractionInput(make_pdf(FRENCH_ONE_CONTAINER), "application/pdf"), CONTEXT)
        .confidence
        == 0.4
    )


def test_an_off_shape_answer_is_a_failed_reading_not_a_half_trusted_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        answer = {"lines": [{"description": "Fret", "amount": "3000.00", "confidence": 4.2}]}
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(answer)}]})

    with pytest.raises(ExtractionFailed) as raised:
        llm(handler).extract(ExtractionInput(make_pdf(FRENCH_ONE_CONTAINER), "application/pdf"), CONTEXT)
    assert raised.value.code == "EXTRACTOR_SHAPE"


def test_a_service_error_is_reported_not_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, text="overloaded")

    with pytest.raises(ExtractionFailed):
        llm(handler).extract(ExtractionInput(make_pdf(FRENCH_ONE_CONTAINER), "application/pdf"), CONTEXT)


def test_the_patterns_are_always_available_and_the_model_only_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import get_settings

    get_settings.cache_clear()
    assert [e.name for e in get_extractors()] == ["regex"]

    monkeypatch.setenv("EXTRACTION_API_KEY", "sk-test")
    get_settings.cache_clear()
    assert [e.name for e in get_extractors()] == ["llm", "regex"]
    get_settings.cache_clear()
