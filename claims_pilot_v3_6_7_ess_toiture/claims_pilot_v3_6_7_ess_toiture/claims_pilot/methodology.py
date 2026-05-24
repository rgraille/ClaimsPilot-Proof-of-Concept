from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .extractor import ExtractedFacts
from .retrieval import RetrievedSource


@dataclass(frozen=True)
class MethodologyAssessment:
    """Résultat du raisonnement expertal structuré.

    Objectif : éviter les décisions par mots-clés isolés. Le moteur doit d'abord
    qualifier le dommage déclaré, puis croiser :
      1. corps d'état / élément affecté,
      2. pathologie,
      3. fiche métier pertinente,
      4. fiche entretien applicable et défaut caractérisé,
      5. gravité décennale.
    """

    corps_etat: str
    element_affecte: str
    pathologie: str
    famille_pathologie: str
    fiche_principale: str
    fiche_entretien_applicable: bool
    defaut_entretien_caracterise: bool
    entretien_kind: str
    entretien_rationale: str
    contre_indices_entretien: List[str]
    gravite_decennale: str
    conclusion_methode: str
    checks: List[str]
    complements: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _low(text: str) -> str:
    return (text or "").lower()


def _has(text: str, *needles: str) -> bool:
    l = _low(text)
    return any(n.lower() in l for n in needles)


def _has_card(retrieved: List[RetrievedSource] | None, card_id: str, limit: int = 5) -> bool:
    return any(r.card.id == card_id for r in (retrieved or [])[:limit])


def _top_card(retrieved: List[RetrievedSource] | None) -> str:
    if retrieved:
        return retrieved[0].card.id
    return "Non déterminée"


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _years_since_reception(facts: ExtractedFacts) -> Optional[float]:
    d1 = _parse_date(facts.reception_date)
    d2 = _parse_date(facts.declaration_date) or _parse_date(facts.loss_date) or datetime.today()
    if not d1 or not d2:
        return None
    return max(0.0, (d2 - d1).days / 365.25)


def _normal_wear_age_gate(facts: ExtractedFacts, element_label: str) -> tuple[bool, list[str], str]:
    """Verrou d'âge commun aux causes d'entretien par usure normale.

    Principe métier V3.6.4 : un défaut d'entretien n'est pas seulement un lien
    vers une fiche entretien. Il suppose un élément normalement soumis à l'usure
    et qui aurait raisonnablement dû être maintenu, contrôlé ou remplacé.
    Dans les deux premières années suivant la réception, l'usure normale ne doit
    pas être la cause dominante par défaut : un mastic, un relevé, une vanne ou
    une pièce d'usure défaillant très tôt oriente d'abord vers un défaut de
    conception, de pose, de calage, de collage, de réglage ou de qualité.
    """
    years = _years_since_reception(facts)
    cautions: list[str] = []
    if years is None:
        cautions.append("âge du sinistre non déterminé : date de réception et date d'apparition/déclaration à confirmer avant d'invoquer l'usure normale")
        return False, cautions, "âge indéterminé"
    if years < 1.0:
        cautions.append("première année après réception : DO mobilisable seulement si mise en demeure GPA restée infructueuse ; l'usure normale n'est pas une cause raisonnable par défaut")
        cautions.append(f"{element_label} défaillant très tôt : rechercher d'abord une origine constructive ou une défaillance initiale")
        return False, cautions, "première année"
    if years < 2.0:
        cautions.append("deux premières années après réception : ne pas opposer un défaut d'entretien par usure normale sans preuve forte d'usage anormal ou d'intervention tierce")
        cautions.append(f"{element_label} défaillant précocement : rechercher d'abord conception, pose, réglage, calage, collage ou qualité d'origine")
        return False, cautions, "deux premières années"
    return True, cautions, "troisième année ou au-delà"


def _severity_counter_indices(text: str, facts: ExtractedFacts) -> List[str]:
    """Indices qui empêchent de réduire trop vite un dossier à l'entretien."""
    l = _low(text)
    indices: List[str] = []
    if _has(l, "logement inférieur", "logement inferieur", "logement en-dessous", "logement du dessous", "local inférieur", "local inferieur"):
        neg_local = re.search(r"(?:sans|absence d['e ]|pas d['e ]).{0,60}(?:logement|local).{0,40}(?:inf[ée]rieur|inferieur|dessous)", l)
        if not neg_local:
            indices.append("conséquences en local inférieur ou logement du dessous")
    if _has(l, "fuite active", "écoulement", "ecoulement", "ruissellement", "humidité active", "humidite active"):
        indices.append("fuite ou humidité active mentionnée")
    if facts.mentions_impropriete or _has(l, "salle de bain inutilisable", "douche inutilisable", "impossible d'utiliser", "ne peut plus utiliser"):
        indices.append("restriction d'usage ou impropriété alléguée")
    if _has(l, "plusieurs logements", "plusieurs appartements", "sériel", "seriel", "récurrent", "recurrent", "réapparu", "reapparu"):
        indices.append("possible récurrence, extension ou risque sériel")
    if facts.mentions_solidite or facts.mentions_safety:
        indices.append("solidité ou sécurité mentionnée")
    return list(dict.fromkeys(indices))


def _shower_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> Optional[MethodologyAssessment]:
    if not (getattr(facts, "mentions_shower_receiver", False) or _has(text, "douche", "receveur", "bac à douche", "bac a douche")):
        return None

    years = _years_since_reception(facts)
    counters = _severity_counter_indices(text, facts)
    periphery = bool(getattr(facts, "mentions_shower_peripheral_joint", False) or _has(text, "périphérie", "peripherie", "pied de cloison", "pied de voile", "plinthe", "joint", "mastic", "silicone"))
    if not (periphery or _has(text, "receveur", "bac à douche", "bac a douche")):
        return None
    localized_consequences = _has(text, "boursouflure", "boursouflures", "ponctuelle", "ponctuelles", "pied de cloison", "plinthe")
    fiche_ok = _has_card(retrieved, "DOUCHE_ZERO_RESSAUT") or periphery

    age_allows_wear, age_cautions, age_label = _normal_wear_age_gate(facts, "mastic souple périphérique / joint sanitaire")
    counters.extend(age_cautions)
    characterized = bool(fiche_ok and periphery and localized_consequences and not counters and age_allows_wear)

    first_year = years is not None and years < 1.0
    first_two_years = years is not None and years < 2.0

    if not age_allows_wear:
        rationale = (
            "Croisement corps d'état / pathologie : receveur de douche + infiltration périphérique + conséquences ponctuelles "
            "en pied de cloison. Le défaut d'entretien par usure normale des mastics n'est pas retenu à ce stade : "
            f"le dossier est en {age_label}. Un mastic périphérique défaillant trop tôt peut révéler un receveur mal calé "
            "ou mobile cisaillant les joints ; le joint du plombier sous le mastic sanitaire doit également jouer son rôle "
            "de seconde barrière. Si l'eau passe, la cause constructive doit être instruite prioritairement."
        )
    else:
        rationale = (
            "Croisement corps d'état / pathologie : receveur de douche + infiltration périphérique + conséquences ponctuelles "
            "en pied de cloison. À partir de la 3e année, cette combinaison peut relever de l'usure normale et de l'entretien "
            "des joints sanitaires : l'absence de maintien en bon état des mastics souples périphériques peut solliciter "
            "anormalement le joint du plombier et devenir la cause dominante."
        )
    if counters:
        rationale += " Points de prudence : " + "; ".join(dict.fromkeys(counters)) + "."

    if characterized:
        gravite = "Gravité décennale non caractérisée : humidité localisée, pas d'infiltration en local inférieur, pas d'impossibilité d'usage ni d'humidité active généralisée mentionnée."
        conclusion = "Non-garantie à proposer pour défaut d'entretien des joints/mastics de douche."
    elif first_year:
        gravite = "Gravité à instruire, mais la DO n'est pas mobilisable en première année sans mise en demeure de l'entrepreneur restée infructueuse au titre de la GPA."
        conclusion = "Déclaration à régulariser au titre de la GPA ; ne pas opposer le défaut d'entretien des mastics."
    elif first_two_years:
        gravite = "Gravité à instruire : dans les deux premières années, l'infiltration périphérique du receveur peut révéler un défaut constructif, même si les conséquences visibles restent ponctuelles."
        conclusion = "Défaut constructif à instruire ; ne pas retenir le défaut d'entretien comme cause dominante."
    else:
        gravite = "Gravité à instruire : la périphérie du receveur oriente vers l'entretien, mais des compléments sont nécessaires avant une position ferme."
        conclusion = "Orientation entretien à vérifier ; ne pas conclure décennal/non décennal sans constats complémentaires ciblés."

    return MethodologyAssessment(
        corps_etat="Salle d'eau / équipement sanitaire",
        element_affecte="Receveur de douche et joints/mastics souples périphériques",
        pathologie="Infiltration localisée en périphérie du receveur avec conséquences ponctuelles en pied de cloison",
        famille_pathologie="Eau / humidité localisée en local humide",
        fiche_principale="DOUCHE_ZERO_RESSAUT",
        fiche_entretien_applicable=fiche_ok,
        defaut_entretien_caracterise=characterized,
        entretien_kind="douche_mastic" if characterized else "",
        entretien_rationale=rationale,
        contre_indices_entretien=counters,
        gravite_decennale=gravite,
        conclusion_methode=conclusion,
        checks=[
            "vérifier visuellement l'état des joints/mastics périphériques du receveur",
            "vérifier le calage du receveur, son éventuel mouvement et le cisaillement des joints",
            "vérifier la continuité du joint du plombier / première barrière sous le mastic sanitaire",
            "confirmer l'absence d'infiltration en logement inférieur",
            "confirmer l'absence d'humidité active ou de perte d'usage de la douche",
            "documenter la chronologie d'apparition et l'évolution des boursouflures",
        ],
        complements=[
            "photos rapprochées du joint périphérique du receveur",
            "photo large de la douche et de la cloison adossée au receveur",
            "test de mise en eau localisé du joint périphérique / pare-douche",
            "vérification du calage et de la stabilité du receveur",
            "constat ou attestation sur l'absence de dégâts en local inférieur",
            "si première année : copie de la mise en demeure de l'entrepreneur au titre de la GPA et preuve de son infructuosité",
        ],
    )



def _top_floor_roof_leak_context(facts: ExtractedFacts, text: str) -> bool:
    l = _low(text)
    damage = _low(getattr(facts, "declared_damage", ""))
    return bool(
        ("fuite" in l or "infiltration" in l or "humid" in l)
        and ("plafond du dernier" in l or "dernier étage" in l or "dernier etage" in l or "plafond" in damage)
        and ("toiture" in l or "terrasse technique" in l or "édicule" in l or "edicule" in l or "dernier étage" in l or "dernier etage" in l)
    )

def _roof_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> Optional[MethodologyAssessment]:
    if not (getattr(facts, "mentions_roof_terrace", False) or _has(text, "toiture", "toiture terrasse", "toiture-terrasse", "terrasse technique", "édicule", "edicule", "relevé d'étanchéité", "releve d'etancheite") or _top_floor_roof_leak_context(facts, text)):
        return None
    fiche_ok = _has_card(retrieved, "ETANCHEITE_TOITURE_TERRASSE_BALCON") or getattr(facts, "mentions_waterproofing_upstand_defect", False)
    age_allows_wear, age_cautions, age_label = _normal_wear_age_gate(facts, "relevé d'étanchéité / point singulier d'étanchéité")
    characterized = bool(age_allows_wear and (getattr(facts, "mentions_characterized_maintenance_defect", False) or (getattr(facts, "mentions_waterproofing_upstand_defect", False) and getattr(facts, "mentions_maintenance_contractor", False))))
    counters = _severity_counter_indices(text, facts) + age_cautions
    if counters and not getattr(facts, "mentions_waterproofing_upstand_defect", False):
        characterized = False
    if age_allows_wear:
        rationale = "Croisement corps d'état / pathologie : toiture-terrasse ou terrasse supérieure + relevé d'étanchéité décollé / point singulier. À partir de la 3e année, la vérification et le maintien du bon état des relevés d'étanchéité peuvent relever strictement de l'entretien dû par la copropriété, si le défaut localisé est caractérisé."
    else:
        rationale = "Croisement corps d'état / pathologie : toiture-terrasse ou terrasse supérieure + relevé d'étanchéité décollé / point singulier. Le défaut d'entretien par usure normale n'est pas retenu à ce stade : en " + age_label + ", un relevé décollé ou un point singulier défaillant oriente d'abord vers un défaut de mise en œuvre, de collage, de protection ou de traitement initial."
    if _top_floor_roof_leak_context(facts, text) and not getattr(facts, "mentions_waterproofing_upstand_defect", False):
        return MethodologyAssessment(
            corps_etat="Étanchéité / toiture / terrasse technique",
            element_affecte="Ouvrages surmontant le plafond du dernier étage (toiture, terrasse technique, édicule, relevés, évacuations EP)",
            pathologie="Résurgence / fuite en plafond du dernier étage, origine sur ouvrages supérieurs non visualisée",
            famille_pathologie="Eau / infiltration par clos-couvert à instruire",
            fiche_principale="ETANCHEITE_TOITURE_TERRASSE_BALCON",
            fiche_entretien_applicable=True,
            defaut_entretien_caracterise=False,
            entretien_kind="",
            entretien_rationale="Le dossier vise une fuite au plafond du dernier étage et une origine toiture/ouvrages surmontants. Le caractère décennal est plausible par atteinte au clos-couvert et à l'usage du logement, mais l'état des ouvrages supérieurs n'est pas visualisé. Aucune cause étrangère ne peut être écartée : entretien des évacuations EP, relevés, solins, équipements techniques, intervention tierce ou défaut localisé doivent être contrôlés.",
            contre_indices_entretien=counters + ["cause étrangère non neutralisée faute de visualisation des ouvrages surmontants"],
            gravite_decennale="Désordre à caractère potentiellement décennal, mais avis garantie non motivable sans constat des ouvrages surmontant le plafond stigmatisé.",
            conclusion_methode="Basculer en ESS ou demander un pack probatoire ciblé permettant de visualiser la toiture/terrasse technique et de neutraliser la cause étrangère.",
            checks=["visualiser la toiture ou terrasse technique au-dessus du plafond", "vérifier édicule, relevés, solins, évacuations EP et équipements techniques", "rechercher une mise en charge ou obstruction", "rattacher précisément la trace intérieure à l'ouvrage supérieur"],
            complements=["photos de la terrasse/toiture et des ouvrages surmontant le plafond", "plan de toiture/terrasse et repérage du logement", "contrat d'entretien toiture/terrasse technique", "dernier compte-rendu de visite du mainteneur", "avis technique ou rapport du mainteneur sur l'origine", "test d'arrosage ou recherche de fuite si nécessaire"],
        )
    return MethodologyAssessment(
        corps_etat="Étanchéité / toiture-terrasse",
        element_affecte="Relevé d'étanchéité ou point singulier de toiture-terrasse",
        pathologie="Infiltration alléguée par défaut localisé de relevé / point singulier",
        famille_pathologie="Eau / infiltration par étanchéité",
        fiche_principale="ETANCHEITE_TOITURE_TERRASSE_BALCON",
        fiche_entretien_applicable=fiche_ok,
        defaut_entretien_caracterise=characterized,
        entretien_kind="roof_upstand" if characterized else "",
        entretien_rationale=rationale,
        contre_indices_entretien=counters,
        gravite_decennale="Gravité décennale neutralisée si le défaut de relevé décollé est retenu comme défaut d'entretien caractérisé ; à réouvrir si infiltration active généralisée ou défaut constructif d'étanchéité est objectivé.",
        conclusion_methode="Non-garantie à proposer pour défaut d'entretien toiture-terrasse." if characterized else "Orientation entretien à vérifier sur point singulier de toiture-terrasse.",
        checks=["constat visuel du relevé décollé", "état des autres relevés / solins", "évacuations EP et absence de mise en charge", "étendue des conséquences intérieures"],
        complements=["photos du relevé", "rapport du mainteneur", "devis détaillé", "historique d'entretien de la terrasse"],
    )


def _mold_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> Optional[MethodologyAssessment]:
    if not getattr(facts, "mentions_mold_condensation", False):
        return None
    fiche_ok = _has_card(retrieved, "VMC_CONDENSATION") or _has(text, "vmc", "ventilation", "bouche", "entrée d'air", "entree d'air")
    age_allows_wear, age_cautions, age_label = _normal_wear_age_gate(facts, "bouches / entrées d'air / organes de ventilation")
    raw_characterized = bool(fiche_ok and _has(text, "bouche encrassée", "bouche encrassee", "débit faible", "debit faible", "entrée d'air bouchée", "entree d'air bouchee", "déficit de vmc", "deficit de vmc"))
    characterized = bool(raw_characterized and age_allows_wear)
    return MethodologyAssessment(
        corps_etat="Ventilation / qualité de l'air intérieur",
        element_affecte="Parement intérieur ponctuellement affecté par moisissures superficielles",
        pathologie="Traces ponctuelles de moisissures compatibles avec condensation / renouvellement d'air insuffisant",
        famille_pathologie="Condensation / ventilation",
        fiche_principale="VMC_CONDENSATION",
        fiche_entretien_applicable=fiche_ok,
        defaut_entretien_caracterise=characterized,
        entretien_kind="vmc_entretien" if characterized else "",
        entretien_rationale=("Croisement corps d'état / pathologie : moisissures ponctuelles + ventilation/VMC. " + ("À partir de la 3e année, le nettoyage des traces et le contrôle/entretien des bouches peuvent relever prioritairement de l'entretien, sauf défaut constructif de VMC objectivé." if age_allows_wear else "Le défaut d'entretien par usure normale n'est pas retenu en " + age_label + " : rechercher d'abord un réglage, un débit initial insuffisant ou une anomalie constructive de ventilation.")),
        contre_indices_entretien=_severity_counter_indices(text, facts) + age_cautions,
        gravite_decennale="Gravité décennale non caractérisée si traces ponctuelles, sans humidité active, généralisation, risque santé objectivé ni perte d'usage.",
        conclusion_methode="Non-garantie / entretien ventilation à privilégier, sous réserve de contrôle VMC." if fiche_ok else "Non décennal probable ; demander contrôle ventilation si doute.",
        checks=["contrôle des débits VMC", "état des bouches et entrées d'air", "évolution saisonnière des traces", "absence d'infiltration active"],
        complements=["photos rapprochées et plan large", "mesure d'humidité", "rapport VMC ou relevé de débit", "chronologie d'apparition / évolution"],
    )


def _plumbing_wear_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> Optional[MethodologyAssessment]:
    if not _has(text, "fuite de vanne", "fuite vanne", "vanne", "robinet", "robinetterie", "siphon", "flexible", "joint de robinet", "pièce d'usure", "piece d'usure", "groupe de sécurité", "groupe de securite"):
        return None
    age_allows_wear, age_cautions, age_label = _normal_wear_age_gate(facts, "vanne / robinetterie / joint / pièce d'usure plomberie")
    wear_fact = _has(text, "usure", "pièce d'usure", "piece d'usure", "joint usé", "joint use", "vanne fuyarde", "robinet fuyard", "remplacement", "mainteneur", "plombier", "devis")
    counters = _severity_counter_indices(text, facts) + age_cautions
    characterized = bool(age_allows_wear and wear_fact and not counters)
    if age_allows_wear:
        rationale = "Croisement corps d'état / pathologie : plomberie + fuite localisée sur vanne, robinetterie, joint ou pièce d'usure. À partir de la 3e année, une défaillance localisée d'un organe normalement soumis à usure peut relever de l'entretien/remplacement courant, si aucun défaut constructif ou dommage étendu n'est objectivé."
    else:
        rationale = "Croisement corps d'état / pathologie : plomberie + fuite localisée sur vanne, robinetterie, joint ou pièce d'usure. Le défaut d'entretien par usure normale n'est pas retenu en " + age_label + " : une fuite aussi précoce oriente d'abord vers un défaut de pose, de serrage, de qualité de l'organe ou de mise en service."
    if counters:
        rationale += " Points de prudence : " + "; ".join(dict.fromkeys(counters)) + "."
    return MethodologyAssessment(
        corps_etat="Plomberie / robinetterie",
        element_affecte="Vanne, robinetterie, joint ou pièce d'usure plomberie",
        pathologie="Fuite localisée d'un organe de plomberie soumis à usure",
        famille_pathologie="Eau / fuite localisée plomberie",
        fiche_principale="PLOMBERIE_RESEAUX",
        fiche_entretien_applicable=True,
        defaut_entretien_caracterise=characterized,
        entretien_kind="plomberie_piece_usure" if characterized else "",
        entretien_rationale=rationale,
        contre_indices_entretien=counters,
        gravite_decennale="Gravité décennale non caractérisée si fuite localisée, sans dommage étendu, sans impropriété ni atteinte à la solidité ; à réouvrir si fuite active importante ou dégâts en local inférieur.",
        conclusion_methode="Non-garantie à proposer pour entretien/remplacement d'une pièce d'usure plomberie." if characterized else "Défaut constructif ou cause initiale à instruire ; ne pas retenir l'usure normale comme cause dominante à ce stade.",
        checks=["identifier l'organe fuyard exact", "vérifier son âge et son état d'usure", "vérifier la pose/serrage/mise en service", "objectiver les conséquences et leur étendue"],
        complements=["photo rapprochée de l'organe fuyard", "rapport ou devis du plombier", "chronologie d'apparition", "constat d'absence de dégâts en local inférieur", "si première année : mise en demeure GPA restée infructueuse"],
    )


def _luminaire_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> Optional[MethodologyAssessment]:
    if not getattr(facts, "mentions_ceiling_suspension", False):
        return None
    return MethodologyAssessment(
        corps_etat="Équipement électrique / luminaire décoratif",
        element_affecte="Luminaire décoratif et fixation au support",
        pathologie="Décrochage ou arrachement localisé d'une fixation avec risque de chute",
        famille_pathologie="Sécurité / chute d'équipement",
        fiche_principale="SUSPENSION_FAUX_PLAFOND_SECURITE",
        fiche_entretien_applicable=False,
        defaut_entretien_caracterise=False,
        entretien_kind="",
        entretien_rationale="Aucune fiche entretien pertinente n'est mobilisée sans indice concret ; la question dominante est le risque de chute et la fixation.",
        contre_indices_entretien=[],
        gravite_decennale="Gravité potentiellement décennale par impropriété à destination liée au risque de chute.",
        conclusion_methode="Garantie possible / intervention de l'entreprise d'origine à solliciter selon quantum et matérialité.",
        checks=["mode de fixation", "support réel", "présence d'autres luminaires identiques", "mise en sécurité"],
        complements=["photo rapprochée de la fixation", "photo large de la zone", "identification du lot électricité", "devis ou intervention proposée"],
    )


def _generic_method(facts: ExtractedFacts, retrieved: List[RetrievedSource] | None, text: str) -> MethodologyAssessment:
    top = _top_card(retrieved)
    return MethodologyAssessment(
        corps_etat="À déterminer par croisement des pièces",
        element_affecte="Élément affecté non verrouillé automatiquement",
        pathologie=facts.declared_damage or "Pathologie non déterminée",
        famille_pathologie="Non déterminée",
        fiche_principale=top,
        fiche_entretien_applicable=bool(top in {"VMC_CONDENSATION", "DOUCHE_ZERO_RESSAUT", "ETANCHEITE_TOITURE_TERRASSE_BALCON"}),
        defaut_entretien_caracterise=False,
        entretien_kind="",
        entretien_rationale="Aucun défaut d'entretien caractérisé n'est retenu : une fiche entretien éventuellement pertinente ne suffit pas sans fait concret rattaché au désordre.",
        contre_indices_entretien=_severity_counter_indices(text, facts),
        gravite_decennale="Gravité décennale à instruire selon solidité, impropriété à destination, sécurité et matérialité des constats.",
        conclusion_methode="Préqualification à valider : compléter la localisation, l'élément atteint, la pathologie et la cause technique.",
        checks=["localisation précise", "élément affecté", "signes visibles", "cause technique probable", "gravité décennale"],
        complements=["photos de loin et de près", "plan ou localisation annotée", "chronologie d'apparition", "devis ou constat technique", "mesures si humidité"],
    )


def assess_methodology(
    facts: ExtractedFacts,
    retrieved: List[RetrievedSource] | None = None,
    raw_text: str = "",
) -> MethodologyAssessment:
    """Applique la démarche expertale dans un ordre verrouillé."""
    text = raw_text or ""
    for builder in (_shower_method, _roof_method, _plumbing_wear_method, _mold_method, _luminaire_method):
        result = builder(facts, retrieved, text)
        if result is not None:
            return result
    return _generic_method(facts, retrieved, text)
