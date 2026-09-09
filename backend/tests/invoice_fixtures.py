"""Three invoices, written as the text a forwarder's PDF actually carries."""

from __future__ import annotations

#: A French forwarder's invoice for one container: THC, ocean freight, customs clearance, VAT.
FRENCH_ONE_CONTAINER = [
    "TRANSITEX SAS",
    "12 quai de la Marine, 76600 Le Havre - TVA FR12345678901",
    "FACTURE N° FA-2026-0912",
    "Date : 12/03/2026",
    "Client : Acme Import SAS",
    "Dossier : MEDUSH2604417   B/L MEDUSH2604417",
    "Conteneur MSCU4821990  40HC",
    "",
    "Designation                                  Quantite   PU        Montant",
    "Fret maritime CNNGB / FRLEH                  1          3 000,00  3 000,00",
    "THC destination Le Havre                     2          137,50    275,00",
    "Dedouanement import                          1          130,00    130,00",
    "Camionnage Le Havre - Rouen                  1          425,00    425,00",
    "",
    "Total HT                                                          3 830,00",
    "TVA 20%                                                             766,00",
    "Total TTC                                                         4 596,00 EUR",
]

#: The same forwarder, two containers on one invoice — the case that needs a human eye.
FRENCH_TWO_CONTAINERS = [
    "TRANSITEX SAS",
    "FACTURE N° FA-2026-0918",
    "Date : 18/03/2026",
    "Dossier : MEDUSH2604417",
    "Conteneurs : MSCU4821990 et TGHU7245081",
    "",
    "THC destination MSCU4821990                                        137,50",
    "THC destination TGHU7245081                                        137,50",
    "Surestaries MSCU4821990 3 jours                                    360,00",
    "Camionnage TGHU7245081                                             425,00",
    "",
    "Total HT                                                         1 060,00",
    "TVA 20%                                                            212,00",
    "Total TTC                                                        1 272,00 EUR",
]

#: An invoice in USD, dated a day for which we have no reference rate in the tests.
USD_INVOICE = [
    "PACIFIC FORWARDING INC",
    "INVOICE No INV-77120",
    "Date: 2026-03-05",
    "Container MSCU4821990",
    "",
    "Ocean freight Ningbo / Le Havre                                 4,200.00",
    "Terminal handling charge                                          310.00",
    "",
    "Total due                                                      4,510.00 USD",
]
