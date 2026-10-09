#!/usr/bin/env python3
"""Write the tester's kit: one made-up importer's last quarter and this week, as the files it would upload.

Terrasses du Ponant SAS (Carquefou, near Nantes) imports garden furniture and outdoor lighting from
China and Vietnam, about three containers a month, and prices them with a flat 1.12 coefficient. The
kit is what its people would hand us: the tariff, the purchase orders, the containers' tracking sheet,
the costs ledger of the last closed quarter as the accountant exports it, and two forwarder invoices —
one for the container discharged this week, one the ledger already holds. `GUIDE.md` walks a tester
through them, screen by screen.

What the files are built to make the application find, on purpose:
- chairs are bulky and cheap: their real coefficient is far above 1.12 (the CFO's surprise);
- parasols and solar lamps share containers: freight split by value or by volume gives two prices;
- container H6 has its terminal handling billed twice by the same forwarder (a sure finding);
- container H5 has a delivery at two and a half times the route's usual price (a question);
- container H7 stayed nine days at the terminal and paid demurrage;
- the ledger holds a credit note, which the import sets aside and says so;
- container L1 was discharged three days ago and is not out: its last free day is tomorrow;
- container L2 is at sea, with no invoice yet: the rate cards estimate it.

Every date is computed from the day this runs (the ledger covers the last closed quarter, the audit's
default window, so it refuses the first four days of a quarter, when L1 would still land in it); no
amount depends on the date. Regenerate before handing the kit to a new tester:

    python3 docs/demo/kit-testeur/generate_kit.py            # Google Chrome renders the PDFs

`backend/tests/test_tester_kit.py` loads the files committed here and pins every figure GUIDE.md quotes.
"""

# ruff: noqa: E501 — the data tables read best one record per line
from __future__ import annotations

import argparse
import csv
import html
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

D = Decimal
ZERO = D("0")
HERE = Path(__file__).parent
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
]

FORWARDER, HAULIER, CLIENT = "MARÉE HAUTE LOGISTIQUE SAS", "TRANSPORTS KERVADEC", "Terrasses du Ponant SAS"
GREENLEAF, SUNCRAFT = "Ningbo Greenleaf Outdoor Co., Ltd", "Ningbo Suncraft Furniture Co., Ltd"
TEAK = "Saigon Teak Craft Co., Ltd"
THC, BROKERAGE = D("285.00"), D("145.00")
SAILING_DAYS = {"Ningbo": 34, "Ho Chi Minh": 30}


@dataclass(frozen=True)
class Product:
    description: str
    hs_code: str
    duty_pct: Decimal
    weight_kg: Decimal
    volume_cbm: Decimal
    sale_price: Decimal


# fmt: off
PRODUCTS = {
    "PAR-300-BEI":  Product("Parasol déporté 3 m beige",        "66011000", D("4.7"), D("14"),  D("0.085"), D("89.00")),
    "LAM-SOL-4":    Product("Lampe solaire LED (lot de 4)",     "94054900", D("4.7"), D("1.2"), D("0.006"), D("14.90")),
    "COU-45-ANT":   Product("Coussin outdoor 45x45 anthracite", "94049000", D("3.7"), D("0.5"), D("0.014"), D("9.90")),
    "CHA-ALU-ANT":  Product("Chaise empilable alu anthracite",  "94017900", D("2.7"), D("4.8"), D("0.110"), D("39.00")),
    "TAB-TECK-180": Product("Table teck 180x90",                "94036010", D("2.7"), D("38"),  D("0.320"), D("549.00")),
}
# fmt: on


@dataclass(frozen=True)
class Order:
    number: int
    supplier: str
    lines: tuple[tuple[str, int, Decimal], ...]  # sku, quantity, FOB unit price


@dataclass(frozen=True)
class Charge:
    """One more line of the ledger, `days` after the box's discharge."""

    days: int
    invoice: str
    label: str
    cost_type: str
    amount: Decimal


@dataclass(frozen=True)
class Box:
    name: str  # H1..H8 in the last quarter, L1/L2 this week: the guide's names, never in a file
    number: str
    carrier: str
    bl: str
    origin: str
    orders: tuple[Order, ...]
    freight: Decimal = ZERO
    drayage: Decimal = ZERO
    days_at_terminal: int = 3
    days_late: int = 0
    extras: tuple[Charge, ...] = ()

    def duty(self) -> Decimal:
        """Customs duty on the CIF value — each line's FOB plus its share of the freight, by value —
        which is what a customs broker pays and what the engine's theoretical duty finds again."""
        lines = [(sku, qty * price) for o in self.orders for sku, qty, price in o.lines]
        fob = sum((value for _, value in lines), ZERO)
        due = sum(
            (PRODUCTS[sku].duty_pct / 100 * value * (1 + self.freight / fob) for sku, value in lines), ZERO
        )
        return due.quantize(D("0.01"), ROUND_HALF_UP)


def order(number: int, supplier: str, *lines: tuple[str, int, str]) -> Order:
    return Order(number, supplier, tuple((sku, qty, D(price)) for sku, qty, price in lines))


# fmt: off
#: The last closed quarter: the day of arrival within the quarter, the box, its forwarder invoice number.
HISTORY = (
    (6, "0412", Box("H1", "MSCU6614208", "MSC", "MEDUNB2601184", "Ningbo",
                    (order(41, GREENLEAF, ("PAR-300-BEI", 600, "38.00")), order(42, GREENLEAF, ("LAM-SOL-4", 1500, "6.50"))),
                    D("3480.00"), D("430.00"))),
    (14, "0427", Box("H2", "MSCU6627740", "MSC", "MEDUNB2601302", "Ningbo",
                     (order(43, SUNCRAFT, ("CHA-ALU-ANT", 520, "21.00")),), D("3520.00"), D("445.00"))),
    (22, "0436", Box("H3", "CMAU4410585", "CMA CGM", "CMDUSGN0884512", "Ho Chi Minh",
                     (order(44, TEAK, ("TAB-TECK-180", 180, "185.00")),), D("3950.00"), D("470.00"))),
    (33, "0451", Box("H4", "MSCU6639016", "MSC", "MEDUNB2601577", "Ningbo",
                     (order(46, GREENLEAF, ("PAR-300-BEI", 560, "38.00"), ("COU-45-ANT", 900, "3.20")),),
                     D("3610.00"), D("420.00"),
                     extras=(Charge(20, "AV-{yy}-0031", "Avoir geste commercial fret", "Fret maritime", D("-80.00")),))),
    (45, "0466", Box("H5", "MSCU6651475", "MSC", "MEDUNB2601790", "Ningbo",
                     (order(47, SUNCRAFT, ("CHA-ALU-ANT", 520, "21.00")),), D("3590.00"), D("1150.00"), days_late=4)),
    (55, "0480", Box("H6", "MSCU6662309", "MSC", "MEDUNB2601926", "Ningbo",
                     (order(49, GREENLEAF, ("PAR-300-BEI", 600, "38.50"), ("LAM-SOL-4", 1500, "6.50")),),
                     D("3700.00"), D("435.00"),
                     extras=(Charge(9, "MHL-{yy}-0498", "THC destination Le Havre", "Manutention portuaire (THC)", THC),))),
    (66, "0503", Box("H7", "CMAU4437293", "CMA CGM", "CMDUSGN0891276", "Ho Chi Minh",
                     (order(50, TEAK, ("TAB-TECK-180", 180, "185.00")),), D("4020.00"), D("465.00"), days_at_terminal=9,
                     extras=(Charge(12, "MHL-{yy}-0521", "Surestaries 4 jours refacturées armateur", "Surestaries",
                                    D("380.00")),))),
    (78, "0517", Box("H8", "MSCU6678835", "MSC", "MEDUNB2602215", "Ningbo",
                     (order(52, SUNCRAFT, ("CHA-ALU-ANT", 520, "21.50")),), D("3640.00"), D("450.00"))),
)
#: Discharged three days ago, still at the terminal: its forwarder's invoice (number 0571) is the one to upload.
L1 = Box("L1", "MSCU6702211", "MSC", "MEDUNB2602688", "Ningbo",
         (order(55, GREENLEAF, ("PAR-300-BEI", 560, "38.50"), ("COU-45-ANT", 900, "3.20")),), D("3780.00"), D("440.00"))
#: At sea, due in nine days: nothing invoiced yet.
L2 = Box("L2", "MSCU6715564", "MSC", "MEDUNB2602841", "Ningbo", (order(58, SUNCRAFT, ("CHA-ALU-ANT", 520, "21.50")),))
# fmt: on


@dataclass(frozen=True)
class Dates:
    etd: date
    eta: date
    ata: date | None = None
    discharged: date | None = None
    gate_out: date | None = None
    empty_returned: date | None = None


def history_dates(arrival: date, box: Box) -> Dates:
    discharged = arrival + timedelta(days=1)
    gate_out = discharged + timedelta(days=box.days_at_terminal)
    etd = arrival - timedelta(days=SAILING_DAYS[box.origin])
    # A late ship: the sheet keeps the ETA first announced.
    eta = arrival - timedelta(days=box.days_late)
    return Dates(etd, eta, arrival, discharged, gate_out, gate_out + timedelta(days=4))


def last_quarter_start(today: date) -> date:
    month = (today.month - 1) // 3 * 3 - 2
    return date(today.year - (month < 1), (month - 1) % 12 + 1, 1)


def fr_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def fr_amount(amount: Decimal) -> str:
    """-12 500,50, the way a French Excel export writes it."""
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def fr_number(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def write_csv(path: Path, header: str, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", lineterminator="\r\n")
        writer.writerow(header.split(";"))
        writer.writerows(rows)


def ordered(dates: Dates) -> date:
    return dates.etd - timedelta(days=50)


def po(o: Order, dates: Dates) -> str:
    """Numbered in the year it was placed, as an ERP numbers it."""
    return f"PO-{ordered(dates):%Y}-{o.number:03d}"


def ledger_lines(box: Box, number: str, discharged: date) -> list[tuple[date, Charge]]:
    """What the accountant's purchase journal holds for one box, by date: the forwarder's invoice, the
    haulier's, and whatever else the box was billed. Each invoice is numbered in the year of its own
    date, as the PDF copy of it is."""
    lines = [
        Charge(2, "MHL-{yy}-" + number, f"Fret maritime {box.origin} - Le Havre", "Fret maritime", box.freight),
        Charge(2, "MHL-{yy}-" + number, "THC destination Le Havre", "Manutention portuaire (THC)", THC),
        Charge(2, "MHL-{yy}-" + number, "Dédouanement import", "Frais de dédouanement", BROKERAGE),
        Charge(2, "MHL-{yy}-" + number, "Débours droits de douane", "Droits de douane", box.duty()),
        Charge(box.days_at_terminal, "TK{yy}" + number, "Camionnage Le Havre - Carquefou", "Camionnage / livraison",
               box.drayage),
        *box.extras,
    ]  # fmt: skip
    dated = [(discharged + timedelta(days=c.days), c) for c in lines]
    return sorted(
        ((on, replace(c, invoice=c.invoice.format(yy=f"{on:%y}"))) for on, c in dated), key=lambda x: x[0]
    )


def invoice_lines(box: Box, dates: Dates, number: str, issued: date, delivery: bool) -> list[str]:
    """The forwarder's invoice as text, one row per line: how the PDF is drawn, and what the rule-based
    reader expects of a table. `delivery`: the forwarder bills the haulage too (else the haulier does)."""
    route = "CNNGB / FRLEH" if box.origin == "Ningbo" else "VNSGN / FRLEH"
    rows = [
        (f"Fret maritime {route}", box.freight),
        ("THC destination Le Havre", THC),
        ("Dedouanement import", BROKERAGE),
        *([("Camionnage Le Havre - Carquefou", box.drayage)] if delivery else []),
        ("Debours droits de douane", box.duty()),
    ]
    total = sum((amount for _, amount in rows), ZERO)
    pad = " " * 61
    return [
        FORWARDER,
        "18 quai Frissard, 76600 Le Havre - Commissionnaire de transport et en douane",
        f"FACTURE N° MHL-{issued:%y}-{number}",
        f"Date : {fr_date(issued)}",
        f"Client : {CLIENT} - 4 rue des Perrieres, 44470 Carquefou",
        f"Dossier : {box.bl}   B/L {box.bl}   Navire arrive le {fr_date(dates.ata)}",
        f"Conteneur {box.number}  40HC   Vos commandes : {', '.join(po(o, dates) for o in box.orders)}",
        "",
        "Designation                                   Quantite   PU            Montant",
        *(f"{label:<45} 1          {fr_amount(a):<13} {fr_amount(a):>10}" for label, a in rows),
        "",
        f"Total HT{pad}{fr_amount(total):>10}",
        f"TVA 0% exoneration art. 262 CGI{' ' * 38}{fr_amount(ZERO):>10}",
        f"Total TTC{pad[1:]}{fr_amount(total):>10} EUR",
    ]


def render_pdf(lines: list[str], path: Path, chrome: str) -> None:
    blank = lines.index("")
    head, table = lines[:blank], lines[blank + 1 :]
    rows = "\n".join(f"<div>{html.escape(line) if line else '&nbsp;'}</div>" for line in table)
    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>{html.escape(head[2])}</title>
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; color: #111; margin: 44px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; color: #0b3b5c; }}
  .sub {{ font-size: 11px; color: #555; margin: 0 0 22px; }}
  p {{ margin: 3px 0; font-size: 13px; }}
  .table {{ font-family: "Courier New", monospace; font-size: 12px; white-space: pre; margin-top: 22px;
            line-height: 1.6; border-top: 2px solid #0b3b5c; padding-top: 6px; }}
  .note {{ margin-top: 40px; font-size: 10px; color: #888; }}
</style></head>
<body>
  <h1>{html.escape(head[0])}</h1>
  <p class="sub">{html.escape(head[1])}</p>
  {"".join(f"<p>{html.escape(line)}</p>" for line in head[2:])}
  <div class="table">
{rows}
  </div>
  <p class="note">Document fictif — jeu de test FreightSight. Aucune société réelle n'est désignée.</p>
</body></html>
"""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "invoice.html"
        source.write_text(page, encoding="utf-8")
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={path}",
        ]
        subprocess.run([*command, source.as_uri()], check=True, capture_output=True)


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Google Chrome not found — install it, or edit CHROME_CANDIDATES in this script")


def write_kit(today: date, out: Path, chrome: str) -> None:
    quarter = last_quarter_start(today)
    history = [
        (box, number, history_dates(quarter + timedelta(days=day), box)) for day, number, box in HISTORY
    ]
    l1_discharged = today - timedelta(days=3)
    l1_arrived = l1_discharged - timedelta(days=1)
    l1 = Dates(l1_arrived - timedelta(days=SAILING_DAYS["Ningbo"]), l1_arrived, l1_arrived, l1_discharged)
    this_quarter = date(today.year, (today.month - 1) // 3 * 3 + 1, 1)
    if l1_arrived < this_quarter:
        # L1 would land in the quarter the ledger covers, and the audit would count it.
        raise SystemExit(f"Too early in the quarter: run this from {this_quarter + timedelta(days=4)} on.")
    l2 = Dates(today - timedelta(days=25), today + timedelta(days=9))
    boxes = [(box, dates) for box, _, dates in history] + [(L1, l1), (L2, l2)]

    write_csv(
        out / "1-tarif.csv",
        "Référence;Désignation;Code SH;Taux de droits;Poids unitaire (kg);Volume unitaire (m³);Prix de vente HT;"
        "Devise de vente",
        [
            [sku, p.description, p.hs_code, fr_number(p.duty_pct), fr_number(p.weight_kg), fr_number(p.volume_cbm),
             fr_amount(p.sale_price), "EUR"]
            for sku, p in PRODUCTS.items()
        ],
    )  # fmt: skip
    write_csv(
        out / "2-commandes.csv",
        "N° commande;Fournisseur;Devise;Date de commande;Incoterm;N° ligne;Référence;Désignation;Quantité;"
        "Prix unitaire",
        [
            [po(o, dates), o.supplier, "EUR", fr_date(ordered(dates)), "FOB", str(n), sku,
             PRODUCTS[sku].description, str(qty), fr_amount(price)]
            for box, dates in boxes
            for o in box.orders
            for n, (sku, qty, price) in enumerate(o.lines, start=1)
        ],
    )  # fmt: skip
    write_csv(
        out / "3-suivi-conteneurs.csv",
        "N° conteneur;Type de conteneur;N° commandes;N° B/L;Compagnie maritime;Port de chargement;"
        "Port de déchargement;ETD;ETA;Arrivée réelle;Déchargé le;Sorti du terminal le;Vide restitué le",
        [
            [box.number, "40HC", ", ".join(po(o, d) for o in box.orders), box.bl, box.carrier, box.origin,
             "Le Havre", *map(fr_date, (d.etd, d.eta, d.ata, d.discharged, d.gate_out, d.empty_returned))]
            for box, d in boxes
        ],
    )  # fmt: skip
    write_csv(
        out / "4-frais-trimestre.csv",
        "Date du coût;Prestataire;N° facture;Libellé;Type de coût;Montant HT;Devise;N° conteneur;N° B/L;N° commande",
        [
            [fr_date(on), HAULIER if c.invoice.startswith("TK") else FORWARDER, c.invoice, c.label, c.cost_type,
             fr_amount(c.amount), "EUR", box.number, "", ""]
            for box, number, dates in history
            if dates.discharged is not None
            for on, c in ledger_lines(box, number, dates.discharged)
        ],
    )  # fmt: skip

    render_pdf(
        invoice_lines(L1, l1, "0571", l1_discharged + timedelta(days=1), delivery=True),
        out / f"5-facture-transitaire-{L1.number}.pdf",
        chrome,
    )
    # Same number, date and lines as the ledger holds: the copy the accountant already booked.
    h8, number, h8_dates = history[-1]
    assert h8_dates.discharged is not None
    render_pdf(
        invoice_lines(h8, h8_dates, number, h8_dates.discharged + timedelta(days=2), delivery=False),
        out / f"6-facture-transitaire-{h8.number}.pdf",
        chrome,
    )


def main() -> int:
    paris_today = datetime.now(ZoneInfo("Europe/Paris")).date()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--today", type=date.fromisoformat, default=paris_today, help="ISO date (default: today)"
    )
    args = parser.parse_args()
    write_kit(args.today, HERE, find_chrome())
    print(f"kit written in {HERE} for {args.today} (ledger: quarter from {last_quarter_start(args.today)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
