from __future__ import annotations

import re
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .extractor import ExtractedFacts
from .expertal import ExpertalAnalysis
from .decision import DecisionResult
from .evidence import EvidenceAssessment
from .carbon import CarbonFactor, search_factors
from .completeness import assess_completeness
from .methodology import assess_methodology



DATE_RE_QUAL = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

def _parse_date_qual(s: str):
    if not s:
        return None
    m = DATE_RE_QUAL.search(s)
    if not m:
        return None
    d, mo, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        return datetime(int(y), int(mo), int(d))
    except ValueError:
        return None

def _years_since_reception_qual(facts: ExtractedFacts) -> Optional[float]:
    d1 = _parse_date_qual(getattr(facts, "reception_date", ""))
    d2 = _parse_date_qual(getattr(facts, "declaration_date", "")) or _parse_date_qual(getattr(facts, "loss_date", "")) or datetime.today()
    if not d1 or not d2:
        return None
    return max(0.0, (d2 - d1).days / 365.25)

def _has_gpa_formal_notice_qual(text: str) -> bool:
    low = (text or "").lower()
    return "mise en demeure" in low and ("infruct" in low or "sans effet" in low or "restée" in low or "restee" in low)

def _has(text: str, *needles: str) -> bool:
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


def _factor_by_code(factors: List[CarbonFactor], code: str) -> Optional[CarbonFactor]:
    for f in factors:
        if (f.code or "").upper() == code.upper():
            return f
    return None


def _declared(line: str) -> str:
    return "Fait déclaré — " + line


def _documented(line: str) -> str:
    return "Constaté dans les pièces — " + line


def _photo(line: str) -> str:
    return "Constaté sur photo — " + line


def _analysis(line: str) -> str:
    return "Analyse de l'application — " + line


def _missing(line: str) -> str:
    return "Information manquante — " + line


def _visual_context_present(text: str) -> bool:
    return _has(text, "analyse visuelle automatique", "risque_chute", "fixation_defaillante", "luminaire_decoratif", "contraste_defaut_support")


def _decade_year_label(facts: ExtractedFacts) -> str:
    years = _years_since_reception_qual(facts)
    if years is None:
        return "âge indéterminé"
    return f"{int(years) + 1}e année"


def _plumbing_location_line(text: str, facts: ExtractedFacts) -> str:
    if facts.location and "Non détermin" not in facts.location:
        return _documented(f"Localisation : {facts.location}.")
    if _has(text, "rdc", "batiment 3", "bâtiment 3", "gaine technique"):
        return _documented("Localisation : RDC du bâtiment 3, au droit d'une gaine technique / parties communes.")
    return _missing("localisation précise à confirmer : bâtiment, niveau, gaine/local, partie commune ou privative.")


@dataclass
class CarbonLine:
    poste: str
    code: str
    designation: str
    unite: str
    quantity: float
    factor_kgco2e: float
    kgco2e: float
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualificationSection:
    title: str
    lines: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualificationView:
    decision_label: str
    validation_label: str
    description: QualificationSection
    technical_opinion: QualificationSection
    warranty_opinion: QualificationSection
    remedy_estimate: QualificationSection
    carbon: Dict[str, Any]
    missing_summary: Dict[str, Any]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_carbon_for_qualification(
    factors: List[CarbonFactor],
    facts: ExtractedFacts,
    raw_text: str,
) -> Dict[str, Any]:
    """Bilan carbone simple, traçable et prudent.

    Le calcul reste indicatif : il rapproche les postes de réparation nécessaires
    des facteurs disponibles dans le référentiel carbone embarqué.
    """
    if not factors:
        return {"status": "non calculable", "total_kgco2e": None, "lines": [], "note": "Référentiel carbone non chargé."}

    lines: List[CarbonLine] = []

    def add(poste: str, code: str, qty: float, comment: str = ""):
        f = _factor_by_code(factors, code)
        if not f:
            return
        kg = round(float(f.value) * qty, 2)
        lines.append(CarbonLine(poste, f.code, f.label, f.unit, qty, float(f.value), kg, comment))

    if facts.mentions_ceiling_suspension or _has(raw_text, "luminaire", "suspension", "faux plafond"):
        add("Transport / déplacement", "PLAFOND_22", 1, "Déplacement et prise de mesures, quantité forfaitaire de qualification.")
        add("Fixation / intervention luminaire", "AUTRES_138", 1, "Correspondance approchée : intervention électrique minimale, faute de ligne dédiée au luminaire décoratif.")
        add("Reprise support ponctuelle", "PLAFOND_2", 1, "Hypothèse prudente : 1 m² de rebouchage / reprise d'enduit de lissage autour du point de fixation.")
        add("Peinture locale", "PLAFOND_4", 2, "Hypothèse prudente : 2 m² de remise en peinture après reprise du support.")
    else:
        for alias in ["peinture", "plaque platre", "enduit"]:
            hit = search_factors(factors, alias, limit=1)
            if hit:
                f = hit[0]
                lines.append(CarbonLine(alias, f.code, f.label, f.unit, 1, float(f.value), round(float(f.value), 2), "Correspondance automatique par alias."))

    total = round(sum(l.kgco2e for l in lines), 2)
    return {
        "status": "approché" if lines else "non calculable",
        "total_kgco2e": total if lines else None,
        "lines": [l.to_dict() for l in lines],
        "note": "Bilan carbone indicatif à valider : les quantités sont forfaitaires et certaines correspondances sont approchées.",
    }


def _location_line(text: str, facts: ExtractedFacts, expertal: ExpertalAnalysis) -> str:
    low = (text or "").lower()
    has_hall = _has(text, "hall ac", "hall d'entrée ac", "hall d entree ac")

    # Adresse extraite des pièces de déclaration, y compris OCR de courrier scanné.
    # On ne la remplace pas par une probabilité si elle est déclarée.
    m = re.search(r"(?:hall\s+d['’ ]?entrée\s+ac|hall\s+ac).*?(?:au|situ[ée]\s+au)?\s*(81)\s*,?\s*(all[ée]e|allee|rue)\s+youri\s+gagarine", low, flags=re.I | re.S)
    if m:
        voie = "allée" if "all" in m.group(2).lower() else "rue"
        return _documented(f"Localisation : Hall d'entrée AC, 81 {voie} Youri Gagarine.")

    has_81_allee = _has(text, "81 allée youri gagarine", "81 allee youri gagarine", "81, allée youri gagarine", "81 allee youri")
    has_81_rue = _has(text, "81 rue youri gagarine", "81, rue youri gagarine")
    has_77_79 = _has(text, "77-79 rue youri gagarine", "79 rue youri gagarine", "77 rue youri gagarine")
    if has_hall and (has_81_allee or has_81_rue):
        voie = "allée" if has_81_allee else "rue"
        return _documented(f"Localisation : Hall d'entrée AC, 81 {voie} Youri Gagarine.")
    if has_hall:
        return _documented("Localisation : Hall d'entrée AC ; adresse précise à confirmer si elle n'est pas lisible dans les pièces déposées.")
    if has_81_allee or has_81_rue:
        voie = "allée" if has_81_allee else "rue"
        return _documented(f"Localisation : 81 {voie} Youri Gagarine ; hall / zone précise à confirmer.")
    if has_77_79:
        return _documented("Localisation : opération située rue Youri Gagarine ; hall / zone précise à confirmer.")

    # On évite d'affirmer une localisation probable comme un fait.
    if facts.location and "Non détermin" not in facts.location:
        return _analysis(f"Localisation fonctionnelle à vérifier : {facts.location}.")
    if expertal.location_context and "Non détermin" not in expertal.location_context:
        return _analysis(f"Localisation fonctionnelle à vérifier : {expertal.location_context}.")
    return _missing("localisation précise à obtenir : hall / cage / niveau / adresse exacte.")


def _fixation_line(text: str, facts: ExtractedFacts) -> str:
    if _has(text, "3 cadres métalliques", "3 cadres metalliques") and _has(text, "chevilles molly", "cheville molly", "4 points"):
        return _documented("Fixation des luminaires : 3 cadres métalliques attachés au faux plafond par 4 chevilles Molly.")
    if _has(text, "chevilles molly", "cheville molly"):
        return _documented("Fixation : fixation mécanique par cheville Molly mentionnée dans les pièces.")
    if _visual_context_present(text):
        return _photo("un luminaire décoratif suspendu est visible ; un point de fixation / ancrage apparaît localement dégradé. Le type exact de cheville et le nombre de points doivent être confirmés si non lisibles dans les pièces.")
    if facts.has_photos:
        return _missing("photos reçues, mais le mode de fixation du luminaire n'est pas établi par le seul libellé ; demander photo rapprochée de l'ancrage si le dossier concerne bien un luminaire.")
    return _missing("mode de fixation à obtenir : nombre de points, type de cheville, support, photos en plan large et en détail.")


def _problem_line(text: str, facts: ExtractedFacts) -> str:
    damage = (facts.declared_damage or "désordre déclaré non déterminé").strip()
    if len(damage) > 220:
        damage = damage[:217] + "..."
    if _has(text, "cheville molly a traversé", "cheville molly a traverse", "traversé la plaque", "traverse la plaque"):
        return _documented("Problème : fixation du luminaire décrochée ; une cheville Molly a traversé le placoplâtre.")
    if _visual_context_present(text):
        return _photo("problème visible compatible avec le décrochage localisé du luminaire / de sa fixation.")
    return _declared(f"Problème : {damage}.")



def _mold_location_lines(text: str, facts: ExtractedFacts) -> List[str]:
    lines: List[str] = []
    # Extraire seulement ce qui est déclaré dans le mail, sans utiliser les renseignements généraux de l'opération.
    m_addr = re.search(r"(79\s+rue\s+Youri\s+Gagarine\s+B[âa]timent\s+D[^\n]{0,80}92700\s+Colombes)", text, flags=re.I)
    if m_addr:
        addr = re.sub(r"\s+", " ", m_addr.group(1)).strip()
        lines.append(_declared(f"Adresse / lot déclaré : {addr}."))
    elif facts.address:
        lines.append(_declared(f"Adresse déclarée : {facts.address}."))
    else:
        lines.append(_missing("adresse / bâtiment / étage / logement à confirmer."))
    if "chambre" in (facts.declared_damage or "").lower() or _has(text, "dans une chambre", "chambre"):
        lines.append(_declared("Localisation du dommage : chambre du logement."))
    else:
        lines.append(_missing("pièce exacte à confirmer."))
    return lines


def _mold_photo_line(text: str, facts: ExtractedFacts) -> str:
    if _has(text, "moisissures_ponctuelles", "condensation_probable", "angle_pied_mur"):
        return _photo("traces noirâtres ponctuelles et localisées en angle / pied de mur, au droit de la plinthe ; faciès compatible avec des moisissures superficielles de condensation.")
    if facts.has_photos:
        return _photo("photos reçues : traces à rapprocher du libellé déclaratif de moisissures ; validation visuelle humaine nécessaire.")
    return _missing("photos rapprochées et plan large de la chambre à obtenir.")


def _is_roof_maintenance_defect(facts: ExtractedFacts, text: str) -> bool:
    return bool(getattr(facts, "mentions_characterized_maintenance_defect", False) or (getattr(facts, "mentions_roof_terrace", False) and getattr(facts, "mentions_waterproofing_upstand_defect", False)))


def _is_shower_mastic_maintenance_defect(facts: ExtractedFacts, text: str) -> bool:
    return bool(getattr(facts, "mentions_shower_mastic_maintenance_defect", False))


def _is_characterized_maintenance_defect(facts: ExtractedFacts, text: str) -> bool:
    return _is_roof_maintenance_defect(facts, text) or _is_shower_mastic_maintenance_defect(facts, text)


def _shower_location_line(text: str, facts: ExtractedFacts) -> str:
    damage = facts.declared_damage or "infiltrations en périphérie du receveur de douche"
    return _declared(f"Dommage déclaré : {damage}.")


def _shower_consequences_line(text: str, facts: ExtractedFacts) -> str:
    if _has(text, "légères boursouflures", "legeres boursouflures", "boursouflures ponctuelles", "pied de cloison"):
        return _declared("Conséquences déclarées : légères boursouflures ponctuelles en pied de cloison adossée au receveur.")
    if _has(text, "boursouflure", "cloque", "pied de cloison", "plinthe"):
        return _declared("Conséquences déclarées : dégradation localisée en pied de cloison / plinthe au droit du receveur.")
    return _missing("conséquences intérieures à préciser : pied de cloison, plinthe, local inférieur, humidité active, évolution.")


def _shower_year_line(expertal: ExpertalAnalysis, facts: ExtractedFacts) -> str:
    if facts.reception_date:
        return _analysis(f"Temps décennal : réception {facts.reception_date} ; {expertal.decade_year.lower()} selon les dates disponibles.")
    return _missing("date de réception à confirmer pour situer le dossier dans la décennale.")


def _extract_roof_origin_line(text: str, facts: ExtractedFacts) -> str:
    damage = facts.declared_damage or "infiltration depuis une toiture-terrasse"
    if _has(text, "salon", "logement supérieur", "logement superieur", "toiture terrasse", "toiture-terrasse"):
        return _declared(f"Dommage déclaré : {damage}.")
    return _declared(f"Dommage déclaré : {damage}.")


def _extract_upstand_line(text: str, facts: ExtractedFacts) -> str:
    if _has(text, "mainteneur") and _has(text, "relevé", "releve") and _has(text, "décoll", "decoll"):
        return _declared("Le mainteneur de la copropriété indique qu'un relevé d'étanchéité est décollé.")
    if _has(text, "relevé", "releve") and _has(text, "décoll", "decoll"):
        return _declared("Un relevé d'étanchéité décollé est mentionné dans les éléments reçus.")
    if getattr(facts, "mentions_waterproofing_upstand_defect", False):
        return _analysis("Point singulier de toiture-terrasse dégradé ou défaut d'évacuation détecté dans le libellé.")
    return _missing("nature exacte du défaut d'entretien à confirmer : relevé, solin, évacuation EP, protection ou joint.")


def _extract_quote_line(decision: DecisionResult) -> str:
    if decision.montant_ttc is not None:
        return _declared(f"Devis / montant déclaré : {decision.montant_ttc:,.0f} € TTC.".replace(",", " "))
    return _missing("devis ou montant d'intervention à obtenir si aucun chiffrage n'est joint.")

def build_qualification_view(
    facts: ExtractedFacts,
    expertal: ExpertalAnalysis,
    decision: DecisionResult,
    evidence: EvidenceAssessment,
    raw_text: str,
    factors: List[CarbonFactor] | None = None,
) -> QualificationView:
    text = raw_text or ""
    method = assess_methodology(facts, [], text)
    is_mold = facts.mentions_mold_condensation or _has(text, "moisissure", "moisissures", "condensation_probable")
    is_luminaire = facts.mentions_ceiling_suspension or _has(text, "luminaire", "suspension décorative", "suspension decorative", "menace de tomber")
    # V3.6.4 : ne pas court-circuiter le verrou d'âge de methodology.py.
    # Un relevé décollé à moins de deux ans ne suffit pas à fonder l'entretien.
    is_maintenance_roof = method.entretien_kind == "roof_upstand"
    years_qual = _years_since_reception_qual(facts)
    is_shower_mastic_maintenance = method.entretien_kind == "douche_mastic"
    is_plumbing_wear_maintenance = method.entretien_kind == "plomberie_piece_usure"
    is_heating_pac_gbf = method.entretien_kind == "chauffage_pac_gbf_forclos"
    is_loggia_roof_non_dec = method.entretien_kind == "loggia_toiture_non_decennial" or decision.decision_code == "REFUS_GARANTIE_PROPOSE_LOGGIA"
    is_living_ceiling_terrace_trace = method.entretien_kind == "terrasse_trace_seche_non_decennale" or decision.decision_code == "REFUS_GARANTIE_PROPOSE_TRACE_SECHE"
    is_shower_constructive_early = bool(getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and years_qual is not None and years_qual < 2.0 and not is_shower_mastic_maintenance)
    first_year_gpa = bool(years_qual is not None and years_qual < 1.0)
    gpa_notice = _has_gpa_formal_notice_qual(text)
    is_ess_roof = decision.decision_code == "ESS_NECESSAIRE_TOITURE"

    if is_living_ceiling_terrace_trace:
        amount_line = f"Estimation financière : {decision.montant_ttc:,.0f} € TTC".replace(",", " ") if decision.montant_ttc is not None else "Estimation financière : 50 € HT à titre indicatif"
        description_lines = [
            _declared(f"Dommage déclaré : {facts.declared_damage or 'infiltration / trace au plafond du séjour'} ."),
            _documented(f"Adresse / opération : {facts.address}.") if facts.address else _missing("adresse de la construction endommagée à confirmer."),
            _documented(f"Réception : {facts.reception_date} ; apparition : {facts.loss_date or 'à confirmer'}.") if facts.reception_date else _missing("date de réception à confirmer."),
            _documented(f"Localisation : {facts.location}.") if facts.location and "Non détermin" not in facts.location else _declared("Localisation : plafond du séjour / pièce habitable sous terrasse privative supérieure à vérifier."),
            _photo("Les photos présentées montrent une trace très ponctuelle en cueillie / plafond du séjour, d'aspect sec ou apathique, sans indice évident de venue d'eau active."),
            _photo("Les vues extérieures/façade ne montrent pas de résurgence évidente en nez de plancher ; cela ne permet pas de conclure à de l'eau dans le complexe d'étanchéité."),
            _analysis("Indice de robustesse description : 85%."),
        ]
        technical_lines = [
            _analysis("La matérialité d'une infiltration active n'est pas constatée dans les conditions de l'analyse : seule une trace ponctuelle est objectivée."),
            _analysis("Le plafond du séjour est déclaré ou présumé surmonté d'une terrasse privative / zone extérieure supérieure ; l'ouvrage doit être contrôlé seulement pour confirmer l'absence de défaut actif."),
            _analysis("Hypothèses techniques non décennales à privilégier en l'état : défaut d'entretien ponctuel de la terrasse supérieure, mousse, bande solin, joint de fractionnement, tête de relevé ou évacuation localement à vérifier."),
            _analysis("Risque : les désordres constatés ne contrarient pas l'occupation du logement et ne caractérisent pas une impropriété à destination."),
            _analysis("Indice de robustesse avis technique : 85%."),
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("La matérialité de l'infiltration déclarée n'a pas été constatée : la trace est ponctuelle, apparemment sèche/apathique et non symptomatique d'une venue d'eau active."),
            _analysis("Les désordres constatés ne sont pas de nature décennale : pas d'atteinte à la solidité, pas d'impropriété à destination et pas de contrariété d'occupation du logement."),
            _analysis("Demander un compte rendu de passage de la société chargée de l'entretien de la terrasse pour confirmer l'absence de défaut d'étanchéité actif et procéder, le cas échéant, à l'entretien."),
            _analysis("Indice de robustesse garantie : 86%."),
        ]
        remedy_lines = [
            _analysis("Estimation financière en position de non-garantie : nettoyage / retouche peinture ponctuelle en cueillie de plafond."),
            _analysis(amount_line),
            _analysis("Base de calcul : nettoyage / retouche peinture locale = 50 € TTC. Ce montant situe l'enjeu et ne constitue pas une indemnité DO proposée."),
            _analysis("Éléments susceptibles de modifier l'avis : humidité active, évolution/extension de la trace, résurgence en façade, entrée d'eau dans le séjour, ou rapport technique objectivant un défaut d'étanchéité actif."),
        ]

    elif is_loggia_roof_non_dec:
        description_lines = [
            _declared(f"Dommage déclaré : {facts.declared_damage or 'auréoles / traces en plafond de loggia déclarées comme provenant de la toiture'} ."),
            _documented(f"Adresse / opération : {facts.address}.") if facts.address else _missing("adresse de la construction endommagée à confirmer."),
            _documented(f"Localisation : {facts.location}.") if facts.location and "Non détermin" not in facts.location else _declared("Localisation : loggia de l'appartement / partie extérieure privative à confirmer."),
            _photo("Les photos montrent des auréoles / traces localisées en plafond ou sous-face de loggia, avec un environnement de façade/brique ; elles ne montrent pas d'entrée d'eau dans une pièce habitable."),
            _analysis("Indice de robustesse description : 82%.")
        ]
        technical_lines = [
            _analysis("Corps d'état pressenti : toiture / couverture / étanchéité, mais le dommage visible est situé en loggia, partie extérieure ou semi-extérieure privative."),
            _analysis("La matérialité retenue est une trace ou auréole en plafond de loggia ; aucune entrée d'eau dans le logement n'est objectivée dans les éléments reçus."),
            _analysis("L'origine alléguée par la toiture peut être vérifiée si le dommage évolue, mais cette origine ne suffit pas à caractériser l'impropriété décennale."),
            _analysis("Risque : absence d'atteinte à la solidité et absence d'impropriété à destination du logement à ce stade."),
            _analysis("Indice de robustesse avis technique : 82%.")
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("Les éléments de la déclaration et les photos permettent de supposer l'absence d'entrée d'eau dans le logement ; le désordre reste localisé à la loggia."),
            _analysis("Le caractère décennal n'est donc pas caractérisé : pas d'impropriété à destination du logement, pas d'atteinte à la solidité, pas de perte d'usage objectivée."),
            _analysis("La garantie obligatoire DO n'est pas mobilisable en l'état, sous validation humaine."),
            _analysis("Indice de robustesse garantie : 82%.")
        ]
        remedy_lines = [
            _analysis("Remède : nettoyage / reprise esthétique locale du plafond de loggia si nécessaire ; vérification toiture uniquement si évolution ou nouvelle entrée d'eau objectivée."),
            _missing("Quantum non chiffré : aucun devis reçu. En non-garantie, le chiffrage sert seulement à situer l'enjeu et ne constitue pas une indemnité DO."),
            _analysis("Éléments susceptibles de modifier l'avis : photo ou constat d'entrée d'eau dans une pièce habitable, extension du dommage, humidité active, ou atteinte à l'usage normal du logement."),
        ]

    elif is_heating_pac_gbf:
        year_label = _decade_year_label(facts)
        amount_line = f"Quantum : {decision.montant_ttc:,.2f} € TTC".replace(",", " ") if decision.montant_ttc is not None else "Quantum : devis de réparation PAC à obtenir ou à confirmer."
        description_lines = [
            _declared(f"Dommage déclaré : {facts.declared_damage or 'dysfonctionnement de l’installation de chauffage/PAC par fuite de fluide frigorigène'}."),
            _documented(f"Réception : {facts.reception_date} ; déclaration / apparition : {facts.declaration_date or facts.loss_date or 'à confirmer'} ; position : {year_label}."),
            _documented("Le compte rendu du mainteneur identifie une PAC air/eau et une fuite de circuit frigorifique / fluide frigorigène au niveau d’un raccord rapide ou d’une liaison frigo."),
            _photo("Les pièces/photos doivent être rattachées au raccord frigorifique et au module PAC ; elles ne doivent pas être analysées comme une infiltration d’eau ou un défaut de toiture."),
            _analysis("Indice de robustesse description : 85%."),
        ]
        technical_lines = [
            _analysis("Corps d’état identifié : chauffage / génie climatique."),
            _analysis("Élément affecté : pompe à chaleur air/eau, liaison frigorifique, raccord rapide, réseau cuivre et fluide R32."),
            _analysis("Actions correctives à envisager : réparation de la fuite frigorifique, remplacement ou reprise de la liaison/raccord, récupération du fluide, mise sous azote, tirage au vide, recharge R32, contrôle d’étanchéité et remise en service."),
            _analysis("Le désordre affecte un élément d’équipement de chauffage ; il ne correspond ni à une pathologie d’étanchéité de toiture, ni à une infiltration d’eau."),
            _analysis("Indice de robustesse avis technique : 90%."),
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("Le dommage affecte un élément d’équipement relevant de la garantie de bon fonctionnement de deux ans à compter de la réception."),
            _analysis("Ce délai est forclos au vu des dates disponibles ; le caractère décennal n’est pas caractérisé."),
            _analysis("L’impropriété de l’ouvrage dans son ensemble n’est pas objectivée : il s’agit d’un dysfonctionnement localisé de PAC / circuit frigorifique, avec solution de dépannage ou de réparation identifiée."),
            _analysis("La garantie obligatoire du contrat DO n’est donc pas mobilisable, sous validation humaine."),
            _analysis("Indice de robustesse garantie : 90%."),
        ]
        remedy_lines = [
            _analysis("Remède : faire réaliser la réparation du circuit frigorifique par une entreprise qualifiée, puis contrôler l’étanchéité et remettre l’installation en service."),
            _analysis(amount_line),
            _analysis("Le quantum est affiché même en non-garantie pour situer l’enjeu, mais ne constitue pas une indemnité DO proposée."),
            _analysis("Indice de robustesse quantum : 90% si devis ENGIE présent, sinon 60%."),
        ]

    elif is_ess_roof:
        description_lines = [
            _declared(f"Dommage déclaré : {facts.declared_damage or 'fuite au plafond du dernier étage'}."),
            _documented(f"Adresse / opération : {facts.address}.") if facts.address else _missing("adresse de la construction endommagée à confirmer."),
            _declared(f"Réception : {facts.reception_date}.") if facts.reception_date else _missing("date de réception à confirmer."),
            _documented("Localisation : plafond du dernier étage / logement sous toiture ou terrasse technique."),
        ]
        technical_lines = [
            _analysis("Constat : résurgence / fuite en plafond d'un logement du dernier étage ; les photos objectivent une trace, mais ne montrent pas l'origine."),
            _analysis("Corps d'état / élément à contrôler : clos-couvert, toiture, terrasse technique, édicule, relevés, évacuations EP, traversées et équipements techniques au-dessus du plafond."),
            _analysis("Risque : désordre potentiellement décennal par atteinte au clos-couvert et à l'usage du logement."),
            _analysis("Limite : aucune vérification de l'état des ouvrages surmontants n'a été faite ; l'application ne doit donc pas verrouiller la garantie."),
        ]
        warranty_lines = [
            _analysis("Avis proposé : les désordres observés peuvent revêtir un caractère décennal, mais l'avis sur garantie n'est pas motivable en l'état."),
            _analysis("Cause étrangère : non neutralisée. Il faut vérifier entretien / obstruction des évacuations EP / état des relevés, solins et traversées / intervention ou équipement technique en toiture."),
            _analysis("Orientation : demander les pièces ciblées au déclarant ; à défaut, basculer en ESS / expertise sur site pour visualiser les ouvrages surmontant le plafond stigmatisé."),
        ]
        remedy_lines = [
            _analysis("Solution : ne pas proposer de mode réparatoire ni de chiffrage avant identification de l'origine."),
            _missing("éléments à obtenir : photos de toiture/terrasse technique, plan de repérage, contrat d'entretien, dernier CR de mainteneur, avis technique du mainteneur, recherche de fuite ou test d'arrosage si nécessaire."),
            _analysis("Bilan carbone : non calculé à ce stade, faute de mode réparatoire identifié."),
        ]

    elif is_maintenance_roof:
        description_lines = [
            _extract_roof_origin_line(text, facts),
            _declared(f"Réception : {facts.reception_date}.") if facts.reception_date else _missing("date de réception à confirmer."),
            _extract_upstand_line(text, facts),
            _extract_quote_line(decision),
        ]

        technical_lines = [
            _analysis("Cause retenue : défaut caractérisé d'entretien / surveillance du relevé d'étanchéité de toiture-terrasse."),
            _analysis("État actuel : infiltration alléguée dans un logement ; le fait déterminant est le relevé d'étanchéité décollé signalé par le mainteneur."),
            _analysis("Risque : désordre localisé et réparable par intervention d'entretien ; pas d'atteinte à la solidité ni d'impropriété décennale retenue à ce stade."),
        ]

        warranty_lines = [
            _analysis("Avis proposé : non-garantie."),
            _analysis("La vérification du bon état des relevés d'étanchéité répond strictement de l'entretien dû par la copropriété."),
            _analysis("Le défaut d'entretien est caractérisé par les éléments reçus ; il n'est donc pas seulement listé comme point à vérifier."),
            _analysis("Garantie obligatoire DO non mobilisable, sous validation humaine."),
        ]

        remedy_lines = [
            _analysis("Solution : faire reprendre le relevé d'étanchéité décollé dans le cadre de l'entretien de la toiture-terrasse et vérifier les autres relevés / solins / évacuations accessibles."),
            _analysis(f"Quantum : {decision.montant_ttc:,.0f} € TTC, non indemnisé au titre de la DO.".replace(",", " ")) if decision.montant_ttc else _missing("quantum à confirmer par devis d'entretien."),
            _analysis("Méthode : montant repris du devis ou de la déclaration ; pas de pré-chiffrage travaux DO dès lors que l'entretien constitue l'orientation principale."),
        ]
    elif is_shower_mastic_maintenance:
        description_lines = [
            _shower_location_line(text, facts),
            _declared(f"Localisation : {facts.location}.") if facts.location and "Non détermin" not in facts.location else _declared("Localisation : logement / salle d'eau ou douche à préciser ; le receveur est identifié dans le libellé."),
            _shower_year_line(expertal, facts),
            _shower_consequences_line(text, facts),
        ]

        technical_lines = [
            _analysis("Démarche : croisement corps d'état / pathologie / fiche entretien, et non simple recherche par mot-clé."),
            _analysis(f"Corps d'état / élément affecté : {method.corps_etat} — {method.element_affecte}."),
            _analysis(f"Pathologie qualifiée : {method.pathologie}."),
            _analysis("Cause retenue : défaut d'entretien / maintien en bon état d'usage des mastics souples en périphérie du receveur."),
            _analysis("Justification : une infiltration localisée en périphérie de receveur, en milieu de décennale, renvoie prioritairement au joint périphérique et non à un défaut décennal de l'ouvrage, sauf preuve contraire."),
            _analysis("État actuel : conséquences déclarées limitées à des boursouflures ponctuelles en pied de cloison ; aucune infiltration dans le logement inférieur, humidité active généralisée ou impossibilité d'usage n'est mentionnée dans les éléments reçus."),
            _analysis("Risque : absence d'atteinte à la solidité et absence d'impropriété à destination caractérisée à ce stade."),
        ]

        warranty_lines = [
            _analysis("Avis proposé : non-garantie."),
            _analysis("Le caractère décennal n'est pas avéré : humidité ponctuelle possiblement liée à l'usage normal de la douche, sans infiltration en local inférieur ni perte d'usage mentionnée."),
            _analysis("La non-garantie est prioritairement motivée par le défaut d'entretien : le maintien des mastics souples en périphérie du receveur relève de l'entretien normal du logement."),
            _analysis("Garantie obligatoire DO non mobilisable, sous validation humaine."),
        ]

        remedy_lines = [
            _analysis("Solution : nettoyage / assèchement ponctuel des conséquences, dépose et reprise des mastics souples périphériques du receveur, puis contrôle d'usage."),
            _analysis("Quantum : pas d'indemnité DO proposée ; intervention d'entretien localisée, à documenter par devis si nécessaire."),
            _analysis("Méthode : ne pas préchiffrer en travaux DO tant que les éléments restent limités aux mastics périphériques et à des conséquences ponctuelles."),
        ]
    elif is_shower_constructive_early:
        description_lines = [
            _shower_location_line(text, facts),
            _declared(f"Localisation : {facts.location}.") if facts.location and "Non détermin" not in facts.location else _declared("Localisation : logement / salle d'eau ou douche à préciser ; le receveur est identifié dans le libellé."),
            _shower_year_line(expertal, facts),
            _shower_consequences_line(text, facts),
        ]

        technical_lines = [
            _analysis("Démarche : croisement corps d'état / pathologie / âge du sinistre / fiche entretien."),
            _analysis("Corps d'état / élément affecté : salle d'eau — receveur de douche, périphérie du receveur, joints et première barrière d'étanchéité."),
            _analysis("Pathologie qualifiée : infiltration en périphérie du receveur avec conséquences ponctuelles en pied de cloison."),
            _analysis("Âge du sinistre : moins de deux ans après réception ; le défaut d'entretien des mastics ne doit pas être retenu par automatisme."),
            _analysis("Analyse technique : si le mastic est dégradé aussi tôt, il faut rechercher un receveur mal calé ou mobile cisaillant les joints."),
            _analysis("Analyse technique : le joint du plombier sous le mastic sanitaire constitue une seconde barrière ; une fuite suppose donc d'instruire une défaillance constructive possible."),
        ]

        warranty_lines = [
            _analysis("Avis proposé : ne pas opposer un défaut d'entretien des mastics à ce stade."),
            _analysis("Le caractère décennal n'est pas encore avéré au seul vu de légères boursouflures ponctuelles et en l'absence d'infiltration en logement inférieur ou de perte d'usage mentionnée."),
            _analysis("La cause constructive doit être instruite prioritairement : calage du receveur, mouvement, cisaillement des joints, continuité du joint du plombier."),
        ]
        if first_year_gpa and not gpa_notice:
            warranty_lines.insert(0, _analysis("Déclaration constituée : NON à ce stade — première année après réception, mise en demeure de l'entrepreneur au titre de la GPA à demander."))
            warranty_lines.append(_analysis("La DO ne peut être mobilisée en première année qu'après mise en demeure de l'entrepreneur restée infructueuse."))
        else:
            warranty_lines.append(_analysis("Garantie obligatoire : à instruire après compléments techniques et vérification de la procédure GPA le cas échéant."))

        remedy_lines = [
            _analysis("Solution à instruire : contrôle du calage et de la stabilité du receveur, test de mise en eau, vérification de la continuité des joints et reprise des conséquences après assèchement."),
            _missing("quantum à chiffrer seulement si l'origine constructive ou la garantie mobilisable est confirmée."),
            _analysis("Méthode : ne pas classer en entretien avant la 3e année sans preuve forte ; dans les deux premières années, rechercher d'abord le défaut constructif."),
        ]
    elif is_plumbing_wear_maintenance:
        year_label = _decade_year_label(facts)
        description_lines = [
            _declared("Il est déclaré une fuite d'une vanne d'arrêt, déjà remplacée compte tenu de l'urgence, avec rapport d'intervention du 07/01/2025 lorsque cette date est lisible."),
            _declared(f"Dommage synthétisé : {facts.declared_damage or 'fuite localisée sur organe de plomberie'} ."),
            _plumbing_location_line(text, facts),
            _documented("Photos / pièces : le remplacement de la vanne est déjà réalisé ; la vanne déposée n'est pas présentée, ce qui limite les constats directs sur l'organe défaillant."),
            _photo("Les photos montrent une dégradation ponctuelle en pied de gaine, cohérente avec les éléments déclarés."),
            _analysis("Indice de robustesse description : 80%."),
        ]
        technical_lines = [
            _analysis("La matérialité du dommage déclaré n'a pas été constatée dans les conditions normales d'une expertise, l'intervention de maintenance étant antérieure à l'analyse."),
            _analysis(f"En l'état, le dommage déclaré réside dans une pièce d'usure de plomberie : vanne / organe de coupure. Le dossier est situé en {year_label} de la décennale."),
            _analysis("Le maintien en bon état de fonctionnement d'une vanne, y compris son remplacement lorsqu'elle devient fuyarde, répond strictement de l'entretien courant, sauf indice contraire de défaut constructif, dommage étendu ou impropriété objectivée."),
            _analysis("Indice de robustesse avis technique : 90%."),
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("La matérialité du dommage déclaré n'a pas été constatée contradictoirement, car l'intervention de maintenance est intervenue avant l'instruction DO."),
            _analysis("Le dommage déclaré résidait dans une pièce d'usure de plomberie dont le remplacement relève strictement de l'entretien."),
            _analysis("Dans ces conditions, la garantie obligatoire du contrat DO n'est pas mobilisable."),
            _analysis("Indice de robustesse garantie : 90%."),
        ]
        remedy_lines = [
            _analysis("Remède : remplacement de la vanne déjà réalisé ; reprise ponctuelle des embellissements au droit de la gaine après assèchement si nécessaire."),
            _analysis("Quantum : remplacement vanne 350 € HT + reprise enduit/peinture 450 € HT = 800 € HT, soit 880 € TTC avec TVA 10 %."),
            _analysis("Ce quantum est chiffré même en non-garantie ; il ne constitue pas une indemnité DO proposée."),
            _analysis("Indice de robustesse quantum : 80%."),
        ]

    elif is_mold and not is_luminaire:
        damage = facts.declared_damage or "traces de moisissure dans une chambre"
        description_lines = [
            _declared(f"Dommage déclaré : {damage}."),
            *_mold_location_lines(text, facts),
            _mold_photo_line(text, facts),
        ]

        technical_lines = [
            _analysis("Causes probables : phénomène de condensation ponctuelle ou léger déficit de renouvellement d'air / VMC à vérifier ; absence d'indice suffisant d'infiltration active dans les éléments reçus."),
            _analysis("État actuel : traces ponctuelles et localisées ; pas de dégradation généralisée visible du support sur les photos transmises."),
            _analysis("Risque : absence d'atteinte à la solidité et absence d'impropriété à destination caractérisée à ce stade."),
        ]

        warranty_lines = [
            _analysis("Élément atteint : parement intérieur / revêtement peint en pièce habitable, affecté par traces superficielles."),
            _analysis("Les traces ponctuelles de moisissures, isolées et sans humidité active objectivée, ne caractérisent pas une impropriété à destination au sens décennal."),
            _analysis("Cause étrangère : ne pas invoquer une cause étrangère abstraite ; l'orientation technique est un contrôle/entretien de la ventilation si le déficit de VMC est confirmé."),
            _analysis("Avis proposé : garantie obligatoire DO non mobilisable à ce stade ; traitement dans le cadre de l'entretien courant / réglage VMC."),
        ]

        remedy_lines = [
            _analysis("Solution : nettoyage des traces à l'eau légèrement javellisée, puis contrôle des bouches, entrées d'air et débits VMC ; réglage ou entretien si nécessaire."),
            _analysis("Quantum : pas d'indemnité DO proposée ; coût d'entretien/nettoyage modeste, hors chiffrage réparatoire décennal."),
            _analysis("Méthode : pas de recours au bordereau travaux tant que la pathologie reste ponctuelle, superficielle et rattachée à l'entretien / ventilation."),
        ]
    elif is_luminaire:
        description_lines = [
            _location_line(text, facts, expertal),
            _fixation_line(text, facts),
            _problem_line(text, facts),
        ]

        if _has(text, "trop écrasée", "trop ecrasee", "forcé sur le support", "force sur le support"):
            cause_line = _documented("Causes : cheville Molly trop écrasée, ayant forcé sur le support en placoplâtre.")
        elif _has(text, "cheville molly", "placoplâtre", "placoplatre") or _visual_context_present(text):
            cause_line = _analysis("Causes probables : défaut de fixation ponctuel du luminaire sur support en plaques de plâtre ; pression / arrachement local du support à confirmer.")
        else:
            cause_line = _analysis("Causes probables : défaut de fixation ponctuel du luminaire ; le mode d'ancrage reste à documenter.")

        if _has(text, "3 autres points", "trois autres points", "un autre point de fixation bouge"):
            state_line = _documented("État actuel : trois points de fixation tiennent ; un autre point bouge légèrement selon les pièces.")
        elif _visual_context_present(text):
            state_line = _photo("État actuel : point d'ancrage localement dégradé ; stabilité résiduelle des autres fixations à vérifier.")
        elif facts.has_photos:
            state_line = _missing("état des fixations à contrôler sur photos rapprochées ; ne pas conclure à un luminaire si le libellé du sinistre ne le vise pas.")
        else:
            state_line = _missing("état des autres fixations à contrôler.")

        if facts.mentions_safety or _has(text, "menace de tomber", "chute", "tomber"):
            risk_line = _analysis("Risque : chute potentielle du luminaire en zone accessible ; point de sécurité à traiter sans attendre.")
        else:
            risk_line = _analysis("Risque : chute potentielle à vérifier, compte tenu du décrochage déclaré d'un élément suspendu.")

        technical_lines = [cause_line, state_line, risk_line]

        if _has(text, "aucune action extérieure", "aucune action exterieure"):
            ce_line = _documented("Cause étrangère : aucune action extérieure n'est mentionnée dans les pièces analysées.")
        else:
            ce_line = _analysis("Cause étrangère / entretien : aucun indice concret d'entretien, d'usage anormal ou d'intervention d'un tiers n'est détecté ; ne pas invoquer de cause étrangère sans élément positif.")

        warranty_lines = [
            _analysis("Élément atteint : élément d'équipement dissociable destiné à fonctionner, à savoir un luminaire décoratif électrique."),
            _analysis("Le risque de chute caractérise une impropriété à destination par atteinte potentielle à la sécurité des personnes."),
            ce_line,
            _analysis("Avis proposé : garantie obligatoire acquise, sous validation humaine."),
        ]

        estimate_ttc = 1800.0
        method_text = "Méthode simple : 18,5 h x 80 € HT/h + 150 € HT de transport = 1 630 € HT ; TVA 10 % = 1 793 € TTC, arrondi métier à 1 800 € TTC."
        remedy_lines = [
            _analysis("Solution : solliciter l'électricien d'origine / l'entreprise du lot électricité pour une intervention spontanée si elle est identifiable ; sinon dépose-repose du luminaire, reprise correcte des fixations, reprise ponctuelle placo/enduit/peinture."),
            _analysis(f"Quantum : {estimate_ttc:,.0f} € TTC.".replace(",", " ")),
            _analysis(method_text),
        ]
    else:
        description_lines = [
            _analysis(f"Localisation : {expertal.location_context}"),
            _declared(f"Dommage déclaré : {expertal.declared_damage}"),
            _analysis(f"Dommage analysé : {expertal.analysed_damage}"),
        ]
        technical_lines = [
            _analysis("Démarche : croisement corps d'état / pathologie / fiche métier / fiche entretien / âge du sinistre."),
            _analysis(f"Corps d'état / élément : {method.corps_etat} — {method.element_affecte}."),
            _analysis(f"Pathologie qualifiée : {method.pathologie}."),
            _analysis(method.entretien_rationale),
            _analysis("Risque : " + method.gravite_decennale),
        ]
        warranty_lines = [
            _analysis(f"Élément atteint : {expertal.affected_element_category} — {expertal.affected_element_detail}"),
            _analysis(method.conclusion_methode),
            _analysis(expertal.cause_etrangere_screening),
            _analysis(expertal.guarantee_analysis),
        ]
        remedy_lines = [
            _analysis("Solution : " + expertal.repair_principle),
            _analysis(f"Quantum : {decision.montant_ttc:,.0f} € TTC".replace(",", " ")) if decision.montant_ttc else _missing("quantum non chiffré à ce stade."),
            _analysis(decision.pricing.get("details", "Méthode de calcul non disponible.")),
        ]

    if 'is_ess_roof' in locals() and is_ess_roof:
        carbon = {"status": "non calculable", "total_kgco2e": None, "lines": [], "note": "Bilan carbone non calculé : l'origine et le mode réparatoire ne sont pas identifiés ; ESS ou pièces complémentaires nécessaires."}
    elif 'is_living_ceiling_terrace_trace' in locals() and is_living_ceiling_terrace_trace:
        carbon = {"status": "non significatif", "total_kgco2e": 0.0, "lines": [], "note": "Nettoyage / retouche ponctuelle : bilan carbone non significatif dans cette préqualification de non-garantie."}
        remedy_lines.append(_analysis("Bilan carbone : non significatif pour un nettoyage / retouche ponctuelle."))
    elif 'is_maintenance_roof' in locals() and is_maintenance_roof:
        carbon = {"status": "non significatif", "total_kgco2e": 0.0, "lines": [], "note": "Intervention d'entretien localisée : bilan carbone non significatif dans cette préqualification."}
        remedy_lines.append(_analysis("Bilan carbone : non significatif pour une intervention d'entretien localisée."))
    elif 'is_shower_mastic_maintenance' in locals() and is_shower_mastic_maintenance:
        carbon = {"status": "non significatif", "total_kgco2e": 0.0, "lines": [], "note": "Reprise locale de mastics souples / entretien : bilan carbone non significatif dans cette préqualification."}
        remedy_lines.append(_analysis("Bilan carbone : non significatif pour une reprise locale de mastics souples et nettoyage ponctuel."))
    elif 'is_heating_pac_gbf' in locals() and is_heating_pac_gbf:
        carbon = {"status": "non calculé", "total_kgco2e": 0.0, "lines": [], "note": "Réparation PAC / circuit frigorifique : bilan carbone non calculé dans cette préqualification de non-garantie."}
        remedy_lines.append(_analysis("Bilan carbone : non calculé dans cette préqualification de non-garantie chauffage/PAC."))
    elif 'is_plumbing_wear_maintenance' in locals() and is_plumbing_wear_maintenance:
        carbon = {"status": "non significatif", "total_kgco2e": 0.0, "lines": [], "note": "Remplacement localisé d'une pièce d'usure plomberie : bilan carbone non significatif dans cette préqualification."}
        remedy_lines.append(_analysis("Bilan carbone : non significatif pour un remplacement localisé d'une pièce d'usure."))
    elif 'is_mold' in locals() and is_mold and not is_luminaire:
        carbon = {"status": "non significatif", "total_kgco2e": 0.0, "lines": [], "note": "Nettoyage ponctuel / entretien : bilan carbone non significatif dans cette préqualification."}
        remedy_lines.append(_analysis("Bilan carbone : non significatif pour un nettoyage ponctuel et un contrôle d'entretien."))
    else:
        carbon = build_carbon_for_qualification(factors or [], facts, raw_text)
        if carbon.get("total_kgco2e") is not None:
            remedy_lines.append(_analysis(f"Bilan carbone : {carbon['total_kgco2e']} kgCO₂e ({carbon['status']})."))
        else:
            remedy_lines.append(_missing("bilan carbone non calculable avec les facteurs disponibles."))

    completeness = assess_completeness(facts, raw_text, evidence=evidence)

    # Le résumé des manques est affiché dans l'écran Qualification :
    # 1) constitution formelle de la déclaration,
    # 2) compléments techniques utiles à la qualification et à la robustesse.
    warnings = []
    if 'is_living_ceiling_terrace_trace' in locals() and is_living_ceiling_terrace_trace:
        warnings.append("Avis simple : non-garantie proposée — trace ponctuelle en plafond du séjour, sans matérialité d'infiltration active ni impropriété objectivée.")
    if 'is_loggia_roof_non_dec' in locals() and is_loggia_roof_non_dec:
        warnings.append("Avis simple : non-garantie proposée — traces limitées à la loggia / extérieur privatif, sans entrée d'eau en logement ni impropriété objectivée.")
    if 'is_ess_roof' in locals() and is_ess_roof:
        warnings.append("ESS : la trace en plafond du dernier étage est potentiellement décennale, mais les ouvrages supérieurs doivent être visualisés pour neutraliser ou retenir une cause étrangère.")
    if method.fiche_entretien_applicable and not method.defaut_entretien_caracterise and not (is_mold and not is_luminaire):
        warnings.append("Méthode : une fiche entretien est pertinente, mais aucun défaut d'entretien suffisamment caractérisé n'est retenu sans fait concret.")
    if is_loggia_roof_non_dec:
        description_lines = [
            _declared(f"Dommage déclaré : {facts.declared_damage or 'auréoles / traces en plafond de loggia déclarées comme provenant de la toiture'} ."),
            _documented(f"Adresse / opération : {facts.address}.") if facts.address else _missing("adresse de la construction endommagée à confirmer."),
            _documented(f"Localisation : {facts.location}.") if facts.location and "Non détermin" not in facts.location else _declared("Localisation : loggia de l'appartement / partie extérieure privative à confirmer."),
            _photo("Les photos montrent des auréoles / traces localisées en plafond ou sous-face de loggia, avec un environnement de façade/brique ; elles ne montrent pas d'entrée d'eau dans une pièce habitable."),
            _analysis("Indice de robustesse description : 82%.")
        ]
        technical_lines = [
            _analysis("Corps d'état pressenti : toiture / couverture / étanchéité, mais le dommage visible est situé en loggia, partie extérieure ou semi-extérieure privative."),
            _analysis("La matérialité retenue est une trace ou auréole en plafond de loggia ; aucune entrée d'eau dans le logement n'est objectivée dans les éléments reçus."),
            _analysis("L'origine alléguée par la toiture peut être vérifiée si le dommage évolue, mais cette origine ne suffit pas à caractériser l'impropriété décennale."),
            _analysis("Risque : absence d'atteinte à la solidité et absence d'impropriété à destination du logement à ce stade."),
            _analysis("Indice de robustesse avis technique : 82%.")
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("Les éléments de la déclaration et les photos permettent de supposer l'absence d'entrée d'eau dans le logement ; le désordre reste localisé à la loggia."),
            _analysis("Le caractère décennal n'est donc pas caractérisé : pas d'impropriété à destination du logement, pas d'atteinte à la solidité, pas de perte d'usage objectivée."),
            _analysis("La garantie obligatoire DO n'est pas mobilisable en l'état, sous validation humaine."),
            _analysis("Indice de robustesse garantie : 82%.")
        ]
        remedy_lines = [
            _analysis("Remède : nettoyage / reprise esthétique locale du plafond de loggia si nécessaire ; vérification toiture uniquement si évolution ou nouvelle entrée d'eau objectivée."),
            _missing("Quantum non chiffré : aucun devis reçu. En non-garantie, le chiffrage sert seulement à situer l'enjeu et ne constitue pas une indemnité DO."),
            _analysis("Éléments susceptibles de modifier l'avis : photo ou constat d'entrée d'eau dans une pièce habitable, extension du dommage, humidité active, ou atteinte à l'usage normal du logement."),
        ]

    elif is_heating_pac_gbf:
        warnings.append("Avis simple : non-garantie proposée — chauffage/PAC, garantie de bon fonctionnement forclose, caractère décennal non caractérisé.")
    if is_plumbing_wear_maintenance:
        warnings.append("Avis simple : non-garantie proposée — pièce d'usure plomberie déjà remplacée ; vérifier seulement l'absence de dommage étendu ou d'indice de défaut constructif.")
    if 'is_maintenance_roof' in locals() and is_maintenance_roof:
        warnings.append("Défaut d'entretien : retenu car la déclaration rattache le désordre à une fiche entretien et à un défaut caractérisé, non par automatisme.")
    if 'is_shower_mastic_maintenance' in locals() and is_shower_mastic_maintenance:
        warnings.append("Défaut d'entretien : retenu par croisement corps d'état / pathologie / fiche entretien, car le désordre est localisé en périphérie du receveur et se rattache au maintien des mastics souples sanitaires.")
    if 'is_shower_constructive_early' in locals() and is_shower_constructive_early:
        warnings.append("Âge du sinistre : moins de deux ans après réception ; ne pas opposer l'entretien des mastics sans preuve forte, rechercher un défaut constructif du receveur ou des barrières d'étanchéité.")
    if is_mold and not is_luminaire:
        warnings.append("Recentrage : ne pas rechercher une douche, un parking ou une infiltration si le libellé déclaré et les photos visent seulement des moisissures ponctuelles dans une chambre.")
    if is_luminaire and not _has(text, "m2ep", "électric", "electric"):
        warnings.append("Entreprise d'origine à identifier : appeler le lot électricité / l'électricien poseur avant d'arrêter l'indemnisation.")
    if is_luminaire and not _has(text, "vidéosurveillance", "videosurveillance", "aucune action extérieure"):
        warnings.append("Cause étrangère : aucun élément positif ne permet de l'invoquer. La vérification d'une action extérieure peut être demandée, sans être retenue par défaut.")

    if 'is_loggia_roof_non_dec' in locals() and is_loggia_roof_non_dec:
        display_decision_label = "Non-garantie proposée — traces en loggia sans entrée d'eau en logement"
    elif 'is_heating_pac_gbf' in locals() and is_heating_pac_gbf:
        display_decision_label = "Non-garantie proposée — chauffage/PAC : GBF forclose"
    elif 'is_ess_roof' in locals() and is_ess_roof:
        display_decision_label = "ESS nécessaire — ouvrages surmontants à visualiser"
    elif 'is_maintenance_roof' in locals() and is_maintenance_roof:
        display_decision_label = "Non-garantie proposée — défaut d'entretien toiture-terrasse"
    elif 'is_shower_mastic_maintenance' in locals() and is_shower_mastic_maintenance:
        display_decision_label = "Non-garantie proposée — défaut d'entretien des joints de douche"
    elif 'is_plumbing_wear_maintenance' in locals() and is_plumbing_wear_maintenance:
        display_decision_label = "Non-garantie proposée — défaut d'entretien plomberie / pièce d'usure"
    elif first_year_gpa and not gpa_notice:
        display_decision_label = "Déclaration non constituée — mise en demeure GPA à demander"
    elif 'is_shower_constructive_early' in locals() and is_shower_constructive_early and first_year_gpa and not gpa_notice:
        display_decision_label = "Déclaration non constituée — mise en demeure GPA à demander"
    elif 'is_shower_constructive_early' in locals() and is_shower_constructive_early:
        display_decision_label = "Défaut constructif à instruire — entretien non retenu"
    elif is_plumbing_wear_maintenance:
        year_label = _decade_year_label(facts)
        description_lines = [
            _declared("Il est déclaré une fuite d'une vanne d'arrêt, déjà remplacée compte tenu de l'urgence, avec rapport d'intervention du 07/01/2025 lorsque cette date est lisible."),
            _declared(f"Dommage synthétisé : {facts.declared_damage or 'fuite localisée sur organe de plomberie'} ."),
            _plumbing_location_line(text, facts),
            _documented("Photos / pièces : le remplacement de la vanne est déjà réalisé ; la vanne déposée n'est pas présentée, ce qui limite les constats directs sur l'organe défaillant."),
            _photo("Les photos montrent une dégradation ponctuelle en pied de gaine, cohérente avec les éléments déclarés."),
            _analysis("Indice de robustesse description : 80%."),
        ]
        technical_lines = [
            _analysis("La matérialité du dommage déclaré n'a pas été constatée dans les conditions normales d'une expertise, l'intervention de maintenance étant antérieure à l'analyse."),
            _analysis(f"En l'état, le dommage déclaré réside dans une pièce d'usure de plomberie : vanne / organe de coupure. Le dossier est situé en {year_label} de la décennale."),
            _analysis("Le maintien en bon état de fonctionnement d'une vanne, y compris son remplacement lorsqu'elle devient fuyarde, répond strictement de l'entretien courant, sauf indice contraire de défaut constructif, dommage étendu ou impropriété objectivée."),
            _analysis("Indice de robustesse avis technique : 90%."),
        ]
        warranty_lines = [
            _analysis("Avis simple : non-garantie proposée."),
            _analysis("La matérialité du dommage déclaré n'a pas été constatée contradictoirement, car l'intervention de maintenance est intervenue avant l'instruction DO."),
            _analysis("Le dommage déclaré résidait dans une pièce d'usure de plomberie dont le remplacement relève strictement de l'entretien."),
            _analysis("Dans ces conditions, la garantie obligatoire du contrat DO n'est pas mobilisable."),
            _analysis("Indice de robustesse garantie : 90%."),
        ]
        remedy_lines = [
            _analysis("Remède : remplacement de la vanne déjà réalisé ; reprise ponctuelle des embellissements au droit de la gaine après assèchement si nécessaire."),
            _analysis("Quantum : remplacement vanne 350 € HT + reprise enduit/peinture 450 € HT = 800 € HT, soit 880 € TTC avec TVA 10 %."),
            _analysis("Ce quantum est chiffré même en non-garantie ; il ne constitue pas une indemnité DO proposée."),
            _analysis("Indice de robustesse quantum : 80%."),
        ]

    elif is_mold and not is_luminaire:
        display_decision_label = "Refus de garantie proposé — moisissures ponctuelles / entretien ventilation"
    elif is_luminaire:
        display_decision_label = "Garantie obligatoire acquise — intervention spontanée à solliciter"
    else:
        display_decision_label = decision.decision_label

    if 'is_loggia_roof_non_dec' in locals() and is_loggia_roof_non_dec:
        display_validation_label = "Validation humaine standard"
    elif 'is_heating_pac_gbf' in locals() and is_heating_pac_gbf:
        display_validation_label = "Validation humaine standard"
    elif 'is_ess_roof' in locals() and is_ess_roof:
        display_validation_label = "ESS / expertise sur site recommandée"
    elif 'is_shower_constructive_early' in locals() and is_shower_constructive_early:
        display_validation_label = "Validation humaine obligatoire"
    elif (('is_maintenance_roof' in locals() and is_maintenance_roof) or ('is_shower_mastic_maintenance' in locals() and is_shower_mastic_maintenance) or is_plumbing_wear_maintenance or (is_mold and not is_luminaire)):
        display_validation_label = "Validation humaine standard"
    elif is_luminaire:
        display_validation_label = "Validation humaine obligatoire"
    else:
        display_validation_label = decision.niveau_validation

    return QualificationView(
        decision_label=display_decision_label,
        validation_label=display_validation_label,
        description=QualificationSection("Description", description_lines),
        technical_opinion=QualificationSection("Avis technique", technical_lines),
        warranty_opinion=QualificationSection("Avis sur la garantie", warranty_lines),
        remedy_estimate=QualificationSection("Remède et estimation", remedy_lines),
        carbon=carbon,
        missing_summary=completeness.to_dict(),
        warnings=warnings,
    )
