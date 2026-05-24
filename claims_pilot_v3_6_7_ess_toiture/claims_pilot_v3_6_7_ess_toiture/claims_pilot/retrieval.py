from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

from .knowledge_base import SourceCard, get_source_cards


def norm(s: str) -> str:
    s = s.lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s


@dataclass
class RetrievedSource:
    card: SourceCard
    score: float
    matched_keywords: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.card.id,
            "famille": self.card.famille,
            "source": self.card.source,
            "score": self.score,
            "matched_keywords": self.matched_keywords,
            "source_detail": self.card.source_detail,
            "card": self.card.to_dict(),
        }


def retrieve_sources(text: str, top_k: int = 4) -> List[RetrievedSource]:
    low = norm(text)
    results: List[RetrievedSource] = []

    shower_terms = ["douche", "receveur", "salle d eau", "salle de bain", "siphon", "caniveau", "mitigeur", "pare douche"]
    roof_terms = ["toiture", "toiture terrasse", "toiture-terrasse", "balcon", "loggia", "acrot", "terrasse toiture", "logement superieur", "logement supérieur", "releve", "relevé", "etancheite", "étanchéité", "eaux pluviales"]
    mold_condensation_terms = ["moisiss", "condensation", "chambre", "piece habitable", "angle_pied_mur", "vmc", "ventilation"]

    for card in get_source_cards():
        matched = []
        score = 0.0
        for kw in card.keywords:
            nkw = norm(kw)

            # Filtres anti-hallucination : un mot générique comme humidité/moisissure
            # ne doit pas déclencher une fiche douche ou toiture sans contexte spécifique.
            if card.id == "DOUCHE_ZERO_RESSAUT" and nkw in {"humidite", "moisissure", "moisissures", "infiltration", "joint"} and not any(t in low for t in shower_terms):
                continue
            if card.id == "ETANCHEITE_TOITURE_TERRASSE_BALCON" and nkw in {"terrasse", "infiltration", "humidite", "humidité"} and not any(t in low for t in roof_terms):
                continue
            if card.id == "FACADE_INFILTRATION" and nkw in {"infiltration", "humidite", "humidité", "mur"} and not any(t in low for t in ["facade", "façade", "fenetre", "fenêtre", "appui", "enduit facade"]):
                continue

            if re.search(r"\b" + re.escape(nkw) + r"\b", low):
                matched.append(kw)
                score += 2.0 if len(nkw) > 6 else 1.0
            elif len(nkw) > 3 and nkw in low:
                matched.append(kw)
                score += 0.75

        # bonus for combined logic patterns
        if card.id == "VMC_CONDENSATION" and any(k in low for k in ["moisiss", "condensation"]):
            # En présence d'une douche/salle de bain, ne basculer VMC que si elle est explicitement nommée
            # ou si le libellé parle vraiment de condensation/air.
            if any(t in low for t in shower_terms) and not any(k in low for k in ["vmc", "ventilation", "condensation", "air"]):
                score += 1
            else:
                score += 8
                if any(k in low for k in ["chambre", "piece habitable", "angle_pied_mur", "pied de mur"]):
                    score += 4
        if card.id == "DOUCHE_ZERO_RESSAUT" and (any(t in low for t in shower_terms) and any(k in low for k in ["humid", "infiltration", "moisiss", "fuite"])):
            score += 10
        if card.id == "CARRELAGE_SOL" and any(k in low for k in ["carrelage", "carreau", "carreaux"]) and any(k in low for k in ["fiss", "decol", "soulev"]):
            score += 5
        if card.id == "FAIENCE_MURALE_SECURITE" and any(k in low for k in ["faience", "faïence", "carreaux", "revetement mural", "revêtement mural"]) and any(k in low for k in ["decol", "décoll", "sonne creux", "chute", "tomber"]):
            score += 7
        if card.id == "NON_CONFORMITE_RESSAUT_RESERVE" and any(k in low for k in ["ressaut", "reserve", "non conform"]):
            score += 5
        if card.id == "SUSPENSION_FAUX_PLAFOND_SECURITE" and any(k in low for k in ["suspension", "luminaire", "élément suspendu", "element suspendu", "menace de tomber", "mise en securite", "risque de chute"]):
            score += 8
        if card.id == "ETANCHEITE_TOITURE_TERRASSE_BALCON" and any(k in low for k in ["releve", "relevé", "etancheite", "étanchéité", "toiture terrasse", "toiture-terrasse"]) and any(k in low for k in ["infiltration", "decol", "décoll", "degrad", "dégrad", "mainteneur", "entretien", "devis"]):
            score += 10

        # Si le focus est clairement moisissures/chambre, ne retenir que les fiches pertinentes.
        if any(k in low for k in ["moisiss", "condensation"]) and not any(t in low for t in shower_terms + roof_terms):
            if card.id in {"DOUCHE_ZERO_RESSAUT", "PLOMBERIE_RESEAUX", "ETANCHEITE_TOITURE_TERRASSE_BALCON"}:
                score = 0.0
                matched = []

        if score > 0:
            results.append(RetrievedSource(card=card, score=round(score, 2), matched_keywords=sorted(set(matched))))
    results = sorted(results, key=lambda r: r.score, reverse=True)
    strong = [r for r in results if r.score >= 3.0]
    return (strong or results)[:top_k]
