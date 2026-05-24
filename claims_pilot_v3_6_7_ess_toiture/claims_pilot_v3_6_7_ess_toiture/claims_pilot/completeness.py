from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from .extractor import ExtractedFacts
from .evidence import EvidenceAssessment

DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


@dataclass
class CompletenessItem:
    code: str
    label: str
    status: str  # OK / MANQUANT / A_VERIFIER / NON_APPLICABLE
    detail: str
    request: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TechnicalItem:
    code: str
    label: str
    status: str  # OK / MANQUANT / A_VERIFIER
    detail: str
    useful_documents: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompletenessAssessment:
    declaration_constituee: bool
    constitution_score: int
    constitution_items: List[CompletenessItem]
    constitution_missing: List[str]
    technical_score: int
    technical_items: List[TechnicalItem]
    technical_missing: List[str]
    useful_documents: List[str]
    summary: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "declaration_constituee": self.declaration_constituee,
            "constitution_score": self.constitution_score,
            "constitution_items": [i.to_dict() for i in self.constitution_items],
            "constitution_missing": self.constitution_missing,
            "technical_score": self.technical_score,
            "technical_items": [i.to_dict() for i in self.technical_items],
            "technical_missing": self.technical_missing,
            "useful_documents": self.useful_documents,
            "summary": self.summary,
        }


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip(" -–:;,.\n\t")


def _parse_numeric_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    m = DATE_NUMERIC_RE.search(s)
    if not m:
        return None
    d, mo, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        return datetime(int(y), int(mo), int(d))
    except ValueError:
        return None


def _extract_email_date(text: str) -> str:
    m = re.search(r"(?:^|\n)Date email\s*:\s*([^\n]+)", text or "", flags=re.I)
    if not m:
        m = re.search(r"(?:^|\n)Date\s*:\s*([^\n]+)", text or "", flags=re.I)
    if m:
        try:
            return parsedate_to_datetime(m.group(1).strip()).strftime("%d/%m/%Y")
        except Exception:
            pass
    return ""


def _date_to_str(d: Optional[datetime]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _extract_contract_number(text: str) -> str:
    patterns = [
        r"(?:concernant\s+le\s+contrat|contrat)\s*n[°o]?\s*([A-Z0-9][A-Z0-9 .\-/]{5,})",
        r"(?:référence\s+du\s+contrat|reference\s+du\s+contrat)[^\n]{0,160}?n[°o]?\s*([A-Z0-9][A-Z0-9 .\-/]{5,})",
        r"(?:contrat\s+(?:dommages?[- ]ouvrage|do)|police|n[°o]\s*de\s*police)[^\n]{0,120}?(?:n[°o]\s*)?([A-Z0-9][A-Z0-9 .\-/]{5,})",
        r"(?:contrat|police)\s*[:\-]\s*(?:n[°o]\s*)?([A-Z0-9][A-Z0-9 .\-/]{5,})",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            value = _clean(m.group(1))
            value = re.sub(r"\s+", "", value)
            if re.search(r"\d{6,}", value):
                return value[:40]
    return ""


def _extract_owner(text: str, facts: ExtractedFacts) -> str:
    patterns = [
        r"coordonn[ée]es?\s+du\s+propri[ée]taire\s*:?\s*\n?\s*([^\n\r]+)",
        r"nom\s+du\s+propri[ée]taire\s*:?\s*([^\n\r]+)",
        r"propri[ée]taire\s*:?\s*([^\n\r]+)",
        r"assur[ée]\s*:?\s*([^\n\r]+)",
        r"b[ée]n[ée]ficiaire\s*:?\s*([^\n\r]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            value = _clean(m.group(1))
            if value and not re.search(r"contrat|police|adresse|date|sinistre", value, flags=re.I):
                return value[:120]
    return _clean(facts.claimant)[:120]


def _extract_address(text: str, facts: ExtractedFacts) -> str:
    # Adresse complète sur une ou plusieurs lignes, sans reprendre le libellé générique de l'opération.
    patterns = [
        r"(\d{1,4}\s+(?:rue|avenue|av\.|all[ée]e|allee|boulevard|bd|chemin|impasse)[^\n\r]{0,120}\n?\s*\d{5}\s+[A-ZÉÈÀÂÎÏÔÛÙÇa-zéèàâêîïôûùç\- ]{2,})",
        r"adresse\s+(?:de\s+la\s+construction|du\s+risque|du\s+bien|endommag[ée]e)?\s*:?\s*([^\n\r]{8,180})",
        r"coordonn[ée]es?\s+du\s+propri[ée]taire[^\n]*\n(?:[^\n]*\n){0,3}?([^\n]*\d{1,4}\s+(?:rue|avenue|all[ée]e|allee)[^\n]*)",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            value = _clean(m.group(1))
            value = re.split(r"\s+-\s+(?:déclaration|declaration|sinistre|dommage)", value, flags=re.I)[0].strip(" -–.;")
            if re.search(r"\d{1,4}.*(rue|avenue|av\.|all[ée]e|allee|boulevard|bd|chemin|impasse)", value, flags=re.I):
                return value[:220]
    return _clean(facts.address)[:220]


def _extract_damage_appearance_date(text: str, facts: ExtractedFacts) -> str:
    patterns = [
        r"date\s+d['’ ]apparition\s+des\s+dommages?\s*:?\s*" + DATE_NUMERIC_RE.pattern,
        r"apparu(?:e|s|es)?\s+(?:le|depuis)?\s*" + DATE_NUMERIC_RE.pattern,
        r"dommages?\s+(?:apparu|survenu|constat[ée])[^\n]{0,90}?" + DATE_NUMERIC_RE.pattern,
        r"sinistre\s+(?:survenu|constat[ée])[^\n]{0,90}?" + DATE_NUMERIC_RE.pattern,
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I | re.S)
        if m:
            nums = re.findall(DATE_NUMERIC_RE, m.group(0))
            if nums:
                d, mo, y = nums[-1]
                if len(y) == 2:
                    y = "20" + y
                try:
                    return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
                except ValueError:
                    pass
    # La date de déclaration ne vaut pas date d'apparition, sauf si le texte parle de survenance le jour même.
    return facts.loss_date or ""


def _has_damage_localization(facts: ExtractedFacts, text: str) -> bool:
    if facts.location and "Non détermin" not in facts.location:
        return True
    damage = (facts.declared_damage or "").lower()
    return any(k in damage for k in ["chambre", "salon", "séjour", "sejour", "cuisine", "salle de bain", "douche", "hall", "toiture", "terrasse", "balcon", "parking", "façade", "facade"])


def _is_gpa_period(facts: ExtractedFacts, text: str) -> Optional[bool]:
    reception = _parse_numeric_date(facts.reception_date)
    event = _parse_numeric_date(facts.declaration_date or "") or _parse_numeric_date(_extract_email_date(text))
    # En saisie manuelle simple, il n'y a souvent pas de date de déclaration.
    # On utilise alors la date du jour pour éviter de manquer la GPA.
    if reception and not event:
        event = datetime.today()
    if not reception or not event:
        return None
    delta_days = (event - reception).days
    return 0 <= delta_days <= 366

def _years_since_reception_for_completeness(facts: ExtractedFacts, text: str) -> Optional[float]:
    reception = _parse_numeric_date(facts.reception_date)
    event = _parse_numeric_date(facts.declaration_date or "") or _parse_numeric_date(_extract_email_date(text))
    if reception and not event:
        event = datetime.today()
    if not reception or not event:
        return None
    return max(0.0, (event - reception).days / 365.25)


def _add_const(items: List[CompletenessItem], code: str, label: str, ok: bool, detail_ok: str, request: str, source: str = "déclaration") -> None:
    if ok:
        items.append(CompletenessItem(code, label, "OK", detail_ok, "", source))
    else:
        items.append(CompletenessItem(code, label, "MANQUANT", request, request, "dossier"))


def _technical_status(ok: bool, verify: bool = False) -> str:
    if ok and not verify:
        return "OK"
    if ok and verify:
        return "A_VERIFIER"
    return "MANQUANT"


def _pathology_identified(facts: ExtractedFacts, text: str = "") -> tuple[bool, str]:
    years = _years_since_reception_for_completeness(facts, text)
    if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        if years is not None and years < 2.0:
            return True, "Pathologie identifiée : infiltration périphérique de receveur ; entretien des mastics non privilégié dans les deux premières années, origine constructive à instruire."
        return True, "Pathologie identifiée : infiltration périphérique de receveur rattachée au maintien des joints/mastics sanitaires."
    if getattr(facts, "mentions_characterized_maintenance_defect", False):
        return True, "Pathologie identifiée : infiltration alléguée rattachée à un défaut de relevé d'étanchéité / entretien toiture-terrasse."
    if getattr(facts, "mentions_mold_condensation", False):
        return True, "Pathologie identifiée : moisissures ponctuelles / condensation ou ventilation à vérifier."
    if getattr(facts, "mentions_ceiling_suspension", False):
        return True, "Pathologie identifiée : décrochage / défaut de fixation d'un élément suspendu."
    if facts.mentions_crack:
        return True, "Pathologie identifiée : fissuration à qualifier."
    if facts.mentions_humidity_or_water:
        return True, "Pathologie générale identifiée : eau / humidité, origine à objectiver."
    if facts.mentions_detachment:
        return True, "Pathologie générale identifiée : décollement / arrachement."
    return False, "La pathologie n'est pas suffisamment qualifiée automatiquement."


def _trade_identification(facts: ExtractedFacts, text: str) -> tuple[bool, str, List[str]]:
    low = (text or "").lower()
    years = _years_since_reception_for_completeness(facts, text)
    if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        if years is not None and years < 2.0:
            return True, "Corps d'état pressenti : plomberie / pose du receveur / calage et barrières d'étanchéité, l'entretien des mastics n'étant pas la piste prioritaire dans les deux premières années.", ["photos rapprochées des joints périphériques", "photo large de la douche et de la cloison concernée", "vérification du calage et du mouvement du receveur", "test de mise en eau", "confirmation d'absence de dégâts en local inférieur", "si première année : mise en demeure GPA restée infructueuse"]
        return True, "Corps d'état pressenti : entretien sanitaire / joints-mastics du receveur de douche.", ["photos rapprochées des joints périphériques", "photo large de la douche et de la cloison concernée", "chronologie d'apparition et d'évolution", "confirmation d'absence de dégâts en local inférieur"]
    if ("plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low) and ("toiture" in low or "fuite" in low or "infiltration" in low):
        return True, "Corps d'état pressenti : étanchéité / toiture / terrasse technique ; origine à objectiver sur les ouvrages surmontant le plafond.", ["photos de la toiture / terrasse technique / édicule", "plan de toiture ou plan de niveau annoté", "photos des relevés, solins, évacuations EP et traversées", "contrat d'entretien et dernier compte-rendu du mainteneur", "recherche de fuite ou test d'arrosage ciblé"]
    if facts.mentions_characterized_maintenance_defect or facts.mentions_roof_terrace:
        return True, "Corps d'état pressenti : étanchéité toiture-terrasse / entretien de la copropriété.", ["devis ou rapport du mainteneur", "contrat ou carnet d'entretien de la toiture-terrasse", "photos du relevé et des évacuations"]
    if facts.mentions_mold_condensation or facts.mentions_vmc:
        return True, "Corps d'état pressenti : ventilation / VMC / entretien des bouches et entrées d'air.", ["dernier rapport d'entretien VMC", "mesure ou relevé des débits", "photos des bouches d'extraction et entrées d'air"]
    if facts.mentions_ceiling_suspension or "luminaire" in low:
        return True, "Corps d'état pressenti : électricité / faux plafond-support à vérifier.", ["DOE ou CCTP du lot électricité", "identité de l'entreprise poseuse", "photos du support et des fixations"]
    if facts.mentions_humidity_or_water:
        return False, "Corps d'état non verrouillé : plomberie / étanchéité / façade selon l'origine.", ["recherche de fuite", "test d'arrosage ou mise en eau", "plan de localisation de la zone humide"]
    return False, "Corps d'état en cause non identifié à ce stade.", ["plans ou DOE utiles", "description précise de l'élément atteint", "photos de situation"]


def assess_completeness(facts: ExtractedFacts, raw_text: str, evidence: Optional[EvidenceAssessment] = None) -> CompletenessAssessment:
    text = raw_text or ""
    constitution_items: List[CompletenessItem] = []

    contract = _extract_contract_number(text)
    owner = _extract_owner(text, facts)
    address = _extract_address(text, facts)
    reception = facts.reception_date
    appearance_date = _extract_damage_appearance_date(text, facts)
    damage_description = bool(_clean(facts.declared_damage))
    damage_location = _has_damage_localization(facts, text)
    gpa = _is_gpa_period(facts, text)
    gpa_formal_notice = bool(re.search(r"mise\s+en\s+demeure|garantie\s+de\s+parfait\s+ach[èe]vement|gpa", text, flags=re.I))

    _add_const(constitution_items, "CONTRAT", "Numéro du contrat d'assurance", bool(contract), f"Numéro détecté : {contract}", "Numéro du contrat DO et, le cas échéant, numéro d'avenant à demander.")
    _add_const(constitution_items, "PROPRIETAIRE", "Nom du propriétaire de la construction endommagée", bool(owner), f"Nom détecté : {owner}", "Nom du propriétaire / bénéficiaire déclarant à demander.")
    _add_const(constitution_items, "ADRESSE", "Adresse de la construction endommagée", bool(address), f"Adresse détectée : {address}", "Adresse complète de la construction endommagée : bâtiment, étage, lot, porte le cas échéant.")
    _add_const(constitution_items, "RECEPTION", "Date de réception ou de première occupation", bool(reception), f"Date détectée : {reception}", "Date de réception des travaux ou, à défaut, date de première occupation des locaux.")
    _add_const(constitution_items, "DATE_APPARITION", "Date d'apparition des dommages", bool(appearance_date), f"Date détectée : {appearance_date}", "Date d'apparition des dommages, ou période d'apparition si la date exacte est inconnue.")
    _add_const(constitution_items, "DESCRIPTION", "Description des dommages", damage_description, f"Description détectée : {_clean(facts.declared_damage)[:180]}", "Description précise du dommage : nature, étendue, fréquence, caractère évolutif ou non.")
    _add_const(constitution_items, "LOCALISATION", "Localisation des dommages", damage_location, f"Localisation détectée : {facts.location if facts.location else 'localisation présente dans le libellé'}", "Localisation précise du dommage : pièce, façade, niveau, bâtiment, partie privative/commune.")

    if gpa is True:
        status = "OK" if gpa_formal_notice else "MANQUANT"
        constitution_items.append(CompletenessItem(
            "GPA_MISE_EN_DEMEURE",
            "Mise en demeure au titre de la GPA",
            status,
            "Copie de la mise en demeure détectée ou mentionnée." if gpa_formal_notice else "Déclaration pendant l'année de parfait achèvement : la copie de la mise en demeure doit être demandée.",
            "Copie de la mise en demeure adressée à l'entreprise au titre de la garantie de parfait achèvement.",
            "déclaration",
        ))
    elif gpa is False:
        constitution_items.append(CompletenessItem("GPA_MISE_EN_DEMEURE", "Mise en demeure au titre de la GPA", "NON_APPLICABLE", "Déclaration hors période de parfait achèvement selon les dates extraites.", "", "analyse"))
    else:
        constitution_items.append(CompletenessItem("GPA_MISE_EN_DEMEURE", "Mise en demeure au titre de la GPA", "A_VERIFIER", "Période de parfait achèvement non vérifiable tant que les dates ne sont pas complètes.", "Si le sinistre est dans l'année suivant la réception, demander la mise en demeure GPA.", "analyse"))

    blocking = [i for i in constitution_items if i.status == "MANQUANT"]
    declaration_constituee = len(blocking) == 0
    applicable = [i for i in constitution_items if i.status != "NON_APPLICABLE"]
    ok_count = sum(1 for i in applicable if i.status == "OK")
    constitution_score = int(round(100 * ok_count / max(1, len(applicable))))

    technical_items: List[TechnicalItem] = []

    loc_ok = damage_location
    loc_verify = loc_ok and (facts.location in {"Pièce habitable", "Façade / extérieur", "Toiture-terrasse / balcon", "Hall / circulations / parties communes"})
    technical_items.append(TechnicalItem(
        "LOCALISATION_FIABLE",
        "Localisation fiable",
        _technical_status(loc_ok, loc_verify),
        "Localisation exploitable, mais à préciser si elle reste générique." if loc_ok else "Localisation insuffisante pour rattacher correctement la pathologie.",
        ["photo de loin avec repère de pièce ou façade", "plan du logement / plan de niveau annoté", "adresse, bâtiment, étage, lot et pièce"],
    ))

    trade_ok, trade_detail, trade_docs = _trade_identification(facts, text)
    technical_items.append(TechnicalItem("CORPS_ETAT", "Corps d'état en cause", _technical_status(trade_ok, not trade_ok), trade_detail, trade_docs))

    path_ok, path_detail = _pathology_identified(facts, text)
    technical_items.append(TechnicalItem(
        "PATHOLOGIE",
        "Pathologie identifiée",
        _technical_status(path_ok, False),
        path_detail,
        ["photos rapprochées nettes", "photos de loin pour rattacher le symptôme à l'ouvrage", "constat technique ou rapport du mainteneur"],
    ))

    nature_ok = damage_description and len(_clean(facts.declared_damage)) >= 20
    nature_verify = nature_ok and not any(k in (facts.declared_damage or "").lower() for k in ["depuis", "apparu", "évolu", "evolu", "ponctuel", "général", "general", "actif"])
    technical_items.append(TechnicalItem(
        "NATURE_TENEUR",
        "Nature et teneur des désordres",
        _technical_status(nature_ok, nature_verify),
        "Description lisible, mais les éléments d'étendue, d'évolution ou de fréquence doivent être complétés." if nature_verify else ("Nature et teneur suffisamment décrites pour une première qualification." if nature_ok else "Description trop pauvre pour apprécier la gravité."),
        ["description libre de l'étendue", "indication du caractère évolutif ou stabilisé", "nombre de zones affectées", "dimensions approximatives"],
    ))

    has_photos = bool(evidence and any(i.code == "PHOTOS" and i.status in {"OBJECTIVE", "RECU"} for i in evidence.items)) or facts.has_photos
    technical_items.append(TechnicalItem(
        "PHOTOS",
        "Photos exploitables",
        _technical_status(has_photos, has_photos),
        "Photos reçues ; prévoir vues complémentaires si elles ne montrent pas l'ensemble et le détail." if has_photos else "Aucune photo exploitable détectée.",
        ["photo de loin", "photo rapprochée", "photo avec échelle / repère", "photo de l'environnement immédiat et des points singuliers"],
    ))

    chrono_ok = bool(appearance_date)
    technical_items.append(TechnicalItem(
        "CHRONOLOGIE",
        "Chronologie et évolution",
        _technical_status(chrono_ok, False),
        "Chronologie minimale disponible." if chrono_ok else "Date d'apparition et évolution non renseignées.",
        ["date ou période d'apparition", "évolution depuis l'apparition", "saisonnalité éventuelle", "témoignage occupant / gardien / syndic"],
    ))

    if facts.mentions_mold_condensation or facts.mentions_vmc:
        technical_items.append(TechnicalItem(
            "VENTILATION_HUMIDITE",
            "Ventilation / humidité",
            "A_VERIFIER",
            "Pour des moisissures ponctuelles, il faut vérifier l'absence d'humidité active et le fonctionnement de la ventilation.",
            ["rapport d'entretien VMC", "mesure de débit des bouches", "photos des entrées d'air et bouches d'extraction", "mesure d'humidité ambiante / support si doute"],
        ))
    elif facts.mentions_humidity_or_water:
        technical_items.append(TechnicalItem(
            "EAU_ORIGINE",
            "Origine eau / humidité",
            "A_VERIFIER",
            "La présence d'eau est alléguée : l'origine doit être objectivée avant garantie.",
            ["recherche de fuite", "test d'arrosage ou mise en eau", "mesures humidimètre", "photos pendant épisode actif"],
        ))

    if facts.has_quote or facts.cost_ttc is not None:
        technical_items.append(TechnicalItem("QUANTUM", "Devis / quantum", "OK", "Un montant ou devis est mentionné dans le dossier.", []))
    else:
        technical_items.append(TechnicalItem("QUANTUM", "Devis / quantum", "A_VERIFIER", "Aucun quantum fiable n'est extrait ; utile surtout en cas de garantie possible ou de TM.", ["devis détaillé", "métré simple", "photos permettant d'apprécier les quantités"]))

    technical_applicable = technical_items
    tech_ok = sum(1 for i in technical_applicable if i.status == "OK")
    tech_partial = sum(1 for i in technical_applicable if i.status == "A_VERIFIER")
    technical_score = int(round((100 * tech_ok + 55 * tech_partial) / max(1, len(technical_applicable))))

    constitution_missing = [i.request for i in constitution_items if i.status == "MANQUANT" and i.request]
    technical_missing = [f"{i.label} : {i.detail}" for i in technical_items if i.status in {"MANQUANT", "A_VERIFIER"}]
    useful_documents: List[str] = []
    for i in technical_items:
        useful_documents.extend(i.useful_documents)
    useful_documents = list(dict.fromkeys([d for d in useful_documents if d]))

    summary = []
    summary.append("Déclaration constituée : OUI" if declaration_constituee else "Déclaration constituée : NON")
    if constitution_missing:
        summary.append("Informations manquantes pouvant justifier une demande de régularisation : " + "; ".join(constitution_missing[:4]))
    else:
        summary.append("Aucun manque bloquant de constitution détecté automatiquement.")
    if technical_missing:
        summary.append("Compléments techniques utiles pour améliorer la robustesse : " + "; ".join(technical_missing[:3]))
    else:
        summary.append("La base technique est suffisante pour une première qualification, sous validation humaine.")

    return CompletenessAssessment(
        declaration_constituee=declaration_constituee,
        constitution_score=constitution_score,
        constitution_items=constitution_items,
        constitution_missing=constitution_missing,
        technical_score=technical_score,
        technical_items=technical_items,
        technical_missing=technical_missing,
        useful_documents=useful_documents,
        summary=summary,
    )
