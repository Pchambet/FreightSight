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
from app.adapters.extraction.regex_extractor import RegexExtractor, describe, last_amount
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

    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 12)
    )
    assert checked.confidence == CAPPED_CONFIDENCE
    assert "@arithmetic_mismatch" in " ".join(checked.notes)


def test_every_line_is_charged_to_the_only_container_named(db: Session, org: Organization) -> None:
    invoice = read(FRENCH_ONE_CONTAINER)
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 12)
    )
    assert [ln.scope for ln in checked.lines] == [CostScope.CONTAINER] * 4
    assert {ln.target_id for ln in checked.lines} == {CONTAINER_A}
    assert all("@single_container|MSCU4821990" in " ".join(ln.notes) for ln in checked.lines)


def test_an_invoiced_cost_of_the_same_type_is_flagged(db: Session, org: Organization) -> None:
    from app.domain.models import (
        AllocationMethod,
        Container,
        ContainerMilestone,
        Cost,
        CostScope,
        CostStatus,
        TrackingState,
    )

    db.add(
        Container(
            id=CONTAINER_A,
            org_id=org.id,
            container_number="MSCU4821990",
            milestone=ContainerMilestone.DISCHARGED,
            tracking_state=TrackingState.MANUAL,
        )
    )
    db.add(
        Cost(
            org_id=org.id,
            scope=CostScope.CONTAINER,
            container_id=CONTAINER_A,
            cost_type=CostType.OCEAN_FREIGHT,
            amount=Decimal("3000.00"),
            currency="EUR",
            fx_rate=Decimal("1"),
            fx_date=date(2026, 3, 1),
            fx_source="same",
            amount_base=Decimal("3000.00"),
            allocation_method=AllocationMethod.BY_WEIGHT,
            cost_date=date(2026, 3, 1),
            status=CostStatus.ACTUAL,
            vendor="Kuehne + Nagel France",
            invoice_number="KN-26-118377",
        )
    )
    db.flush()

    invoice = read(FRENCH_ONE_CONTAINER)
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 12)
    )
    freight = next(ln for ln in checked.lines if ln.cost_type == CostType.OCEAN_FREIGHT)
    assert any(n.startswith("@duplicate_cost|OCEAN_FREIGHT|") for n in freight.notes)
    assert freight.confidence <= CAPPED_CONFIDENCE


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
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 12)
    )
    (line,) = checked.lines
    assert line.scope is None and line.target_id is None
    assert line.confidence <= CAPPED_CONFIDENCE
    assert "@unknown_container|ZZZU0000000" in " ".join(line.notes)


def test_a_currency_without_a_rate_marks_the_line_for_review(db: Session, org: Organization) -> None:
    invoice = read(USD_INVOICE)
    assert invoice.currency == "USD"
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 5)
    )
    assert checked.lines  # the charges were read
    for line in checked.lines:
        assert line.currency == "USD"
    # the fake fetcher knows USD, so nothing is flagged; an unknown currency is another story
    invoice.lines[0].currency = "SEK"
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 5)
    )
    assert "@no_fx_rate|SEK" in " ".join(checked.lines[0].notes)
    assert checked.lines[0].confidence <= CAPPED_CONFIDENCE


def test_several_containers_asks_for_a_second_look(db: Session, org: Organization) -> None:
    invoice = read(FRENCH_TWO_CONTAINERS)
    checked = check(
        db, fx(), invoice, CONTEXT, org_id=org.id, base_currency="EUR", invoice_date=date(2026, 3, 18)
    )
    assert "@multi_container" in " ".join(checked.notes)
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


# ---------------------------------------------------------------------------- a real invoice


def test_a_real_forwarder_invoice_reads_exactly(db: Session, org: Organization) -> None:
    """The one fixture nobody wrote to be easy: a French forwarder invoice produced for a production
    walkthrough, which caught two bugs the invented ones did not — a header line naming a B/L and a
    container size, and a VAT line stating its taxable base."""
    from pathlib import Path

    pdf = (Path(__file__).parent / "fixtures" / "facture_transitaire_fr.pdf").read_bytes()
    invoice = RegexExtractor().extract(
        ExtractionInput(pdf, "application/pdf", "facture_transitaire_fr.pdf"), CONTEXT
    )

    assert invoice.invoice_number == "FAC-2026-08871"
    assert invoice.invoice_date == date(2026, 9, 5)
    # The three totals the invoice prints, each read rather than inferred from the others.
    assert invoice.subtotal == "3350.00"
    assert invoice.vat == "167.00"  # computed as TTC - HT, not read off the label
    assert invoice.total == "3517.00"
    assert invoice.container_numbers == ["MSCU1234567"]

    charges = [(ln.cost_type, ln.amount) for ln in invoice.lines]
    assert charges == [
        (CostType.OCEAN_FREIGHT, "2450.00"),
        (CostType.THC, "285.00"),
        (CostType.BL_FEE, "65.00"),
        (CostType.CUSTOMS_BROKERAGE, "120.00"),
        (CostType.DRAYAGE, "430.00"),
    ]
    # and what a reviewer reads is the charge, not the table's quantity and unit-price columns
    assert [ln.description for ln in invoice.lines] == [
        "Fret maritime Shanghai / Le Havre (Ocean freight)",
        "THC destination Le Havre (Terminal Handling Charges)",
        "Frais de B/L (Bill of lading fee)",
        "Dédouanement import (customs brokerage)",
        "Camionnage Le Havre →  entrepôt client (drayage)",
    ]
    holds, difference = arithmetic_holds(invoice)
    assert holds and difference == Decimal("0.00")


def test_the_description_keeps_the_wording_and_drops_the_columns() -> None:
    """A table row is wording followed by quantity, unit price and amount. Only a run of numbers
    that reaches the end of the line is a set of columns; one inside the wording is part of it."""
    assert (
        describe("Fret maritime Shanghai / Le Havre (Ocean freight) 1 2 450,00 2 450,00")
        == "Fret maritime Shanghai / Le Havre (Ocean freight)"
    )
    assert describe("THC destination Le Havre 1 285,00 285,00") == "THC destination Le Havre"
    # a quantity that belongs to the wording survives, because words follow it
    assert describe("Surestaries 5 jours x 80,00 400,00") == "Surestaries 5 jours"
    # the sign of a multiplication goes; the last letter of a word that happens to be x stays
    assert describe("Camionnage Bordeaux 1 250,00 250,00") == "Camionnage Bordeaux"
    # the currency the last column ends with is not a reason to give up and show the whole row
    assert describe("Dédouanement import 120,00 €") == "Dédouanement import"
    assert describe("Frais de B/L 65,00 EUR") == "Frais de B/L"
    assert describe("Conteneur 40' HC — manutention 150,00") == "Conteneur 40' HC — manutention"
    # nothing to cut, nothing cut
    assert describe("Frais de dossier") == "Frais de dossier"
    # and a row that is only numbers keeps something rather than becoming empty
    assert describe("1 2 450,00 2 450,00") == "1 2 450,00 2 450,00"


def test_a_missed_line_is_caught_by_the_invoice_s_own_pre_tax_total() -> None:
    """The failure that matters: a charge the patterns did not recognise.

    Against the grand total it hides behind the VAT — when the tax cannot be read, a total short by
    exactly the missing charge looks like a total short by exactly the tax. The invoice's own
    « Total HT » has no such excuse in it.
    """
    missing_the_bl_fee = FreightInvoice(
        currency="EUR",
        subtotal="3350.00",
        vat=None,  # unreadable, as it is on plenty of layouts
        total="3517.00",
        lines=[
            ExtractedLine(description="Fret maritime", amount="2450.00"),
            ExtractedLine(description="THC", amount="285.00"),
            ExtractedLine(description="Dédouanement", amount="120.00"),
            ExtractedLine(description="Camionnage", amount="430.00"),
        ],
    )
    holds, difference = arithmetic_holds(missing_the_bl_fee)
    assert not holds
    assert difference == Decimal("-65.00")  # exactly the charge nobody saw

    complete = missing_the_bl_fee.model_copy(
        update={
            "lines": [
                *missing_the_bl_fee.lines,
                ExtractedLine(description="Frais de B/L", amount="65.00"),
            ]
        }
    )
    holds, difference = arithmetic_holds(complete)
    assert holds and difference == Decimal("0.00")


def test_without_a_stated_pre_tax_total_the_old_check_still_applies() -> None:
    """Not every invoice prints one; the grand total is then the only yardstick there is."""
    invoice = FreightInvoice(
        currency="EUR",
        total="3517.00",
        vat="167.00",
        lines=[ExtractedLine(description="Fret maritime", amount="3350.00")],
    )
    holds, difference = arithmetic_holds(invoice)
    assert holds and difference == Decimal("0.00")


def test_a_header_naming_a_charge_is_not_a_charge() -> None:
    """« … · B/L MEDUSH2604417 · Conteneur MSCU1234567 (40' HC) · Navire … » once became a
    bill-of-lading fee of 40. A charge line ends on its amount; a sentence does not."""
    from app.adapters.extraction.regex_extractor import trailing_amount

    header = "Dossier import LEH-26-4417 · B/L MEDUSH2604417 · Conteneur MSCU1234567 (40' HC) · Navire"
    assert trailing_amount(header) is None
    assert trailing_amount("Frais de B/L (Bill of lading fee) 1 65,00 65,00") == Decimal("65.00")
    assert trailing_amount("Total TTC 3 517,00 EUR") == Decimal("3517.00")


def test_a_registration_number_is_not_an_amount_of_tax() -> None:
    lines = [
        "TRANSITEX SAS - TVA FR12812345678",
        "Fret maritime 2 400,00",
        "Total HT 2 400,00",
        "TVA 20 % (sur prestations taxables : 835,00) 167,00",
        "Total TTC 2 567,00",
    ]
    invoice = read(lines)
    assert invoice.vat == "167.00"
