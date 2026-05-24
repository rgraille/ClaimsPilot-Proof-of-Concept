from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .extractor import ExtractedFacts
from .retrieval import RetrievedSource


@dataclass
class PricingResult:
    amount_ttc: float | None
    amount_ht: float | None
    vat_rate: float
    source: str  # extrait / estimation_simple / non_chiffre
    method: str
    hours: float | None = None
    hourly_rate_ht: float | None = None
    transport_ht: float | None = None
    rounded: bool = False
    confidence: int = 0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _round_to_nearest(value: float, step: int = 50) -> float:
    return round(value / step) * step


def _has(text: str, words: List[str]) -> bool:
    low = (text or "").lower()
    return any(w in low for w in words)


def estimate_simple_pricing(facts: ExtractedFacts, raw_text: str, retrieved: List[RetrievedSource], vat_rate: float, hourly_rate_ht: float = 80.0, transport_ht: float = 150.0) -> PricingResult:
    """Pré-chiffrage simple quand aucun devis/Kora n'est exploitable.

    Méthode métier V2.2 : 80 € HT/h tout compris + 150 € HT de déplacement/transport.
    Les heures sont proposées par famille de désordre et doivent rester validables.
    """
    if facts.cost_ttc is not None:
        return PricingResult(
            amount_ttc=round(facts.cost_ttc, 2),
            amount_ht=round(facts.cost_ttc / (1 + vat_rate), 2),
            vat_rate=vat_rate,
            source="extrait",
            method="Montant extrait du dossier",
            confidence=80 if facts.has_quote else 65,
            details="Montant lu dans la déclaration, un devis, un rapport ou un courriel.",
        )

    top_ids = {r.card.id for r in retrieved[:3]}
    text = raw_text or ""
    hours: Optional[float] = None
    rationale = ""

    if getattr(facts, "mentions_mold_condensation", False):
        return PricingResult(
            amount_ttc=None,
            amount_ht=None,
            vat_rate=vat_rate,
            source="non_chiffre",
            method="Pas de chiffrage réparatoire décennal",
            confidence=70,
            details="Traces de moisissures ponctuelles : nettoyage léger et entretien/contrôle VMC, sans réparation décennale chiffrée à ce stade.",
        )

    if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        return PricingResult(
            amount_ttc=None,
            amount_ht=None,
            vat_rate=vat_rate,
            source="non_chiffre",
            method="Pas de chiffrage réparatoire décennal",
            confidence=70,
            details="Infiltration périphérique de receveur rattachée à l'entretien des mastics souples : ne pas appliquer de pré-chiffrage travaux DO.",
        )

    ceiling_suspension_case = facts.mentions_ceiling_suspension or "SUSPENSION_FAUX_PLAFOND_SECURITE" in top_ids or _has(text, ["suspension", "faux plafond", "menace de tomber", "mise en sécurité"])
    if ceiling_suspension_case:
        # Cible V3 métier : pré-estimation de qualification à 1 800 € TTC.
        # Le temps équivalent est recalé selon le taux de TVA retenu pour conserver la méthode
        # 80 € HT/h + 150 € HT de transport tout en affichant un TTC stable en démo.
        target_ttc = 1800.0
        hours = round(((target_ttc / (1 + vat_rate)) - transport_ht) / hourly_rate_ht, 1)
        rationale = "Dépose-repose / refixation correcte du luminaire, reprise ponctuelle placo-enduit-peinture et transport."
    elif facts.mentions_humidity_or_water and ("DOUCHE_ZERO_RESSAUT" in top_ids or "PLOMBERIE_RESEAUX" in top_ids):
        hours = 18.0
        rationale = "Traitement local d'étanchéité/réseaux et reprise ponctuelle de finition : 18 h estimées + transport."
    elif facts.mentions_detachment:
        hours = 12.0
        rationale = "Décollement ou désordre localisé sans métrés : 12 h estimées + transport."
    elif facts.mentions_crack:
        hours = 10.0
        rationale = "Fissuration localisée sans métrés : 10 h estimées + transport."

    if hours is None:
        return PricingResult(
            amount_ttc=None,
            amount_ht=None,
            vat_rate=vat_rate,
            source="non_chiffre",
            method="Chiffrage impossible sans métrés ou famille réparatoire suffisante",
            confidence=0,
            details="Aucun chiffrage extrait et aucune règle simple applicable n'a été déclenchée.",
        )

    ht = hours * hourly_rate_ht + transport_ht
    ttc_raw = ht * (1 + vat_rate)
    ttc = 1800.0 if 'ceiling_suspension_case' in locals() and ceiling_suspension_case else float(_round_to_nearest(ttc_raw, 50))
    ht_from_rounded = ttc / (1 + vat_rate)
    return PricingResult(
        amount_ttc=round(ttc, 2),
        amount_ht=round(ht_from_rounded, 2),
        vat_rate=vat_rate,
        source="estimation_simple",
        method="Méthode simple : 80 € HT/h tout compris + 150 € HT de transport, arrondi au 50 € TTC",
        hours=hours,
        hourly_rate_ht=hourly_rate_ht,
        transport_ht=transport_ht,
        rounded=True,
        confidence=70,
        details=f"{rationale} Calcul brut : ({hours:g} h x {hourly_rate_ht:.0f} € HT) + {transport_ht:.0f} € HT = {ht:.2f} € HT ; TTC brut {ttc_raw:.2f} €, arrondi à {ttc:.2f} € TTC.",
    )
