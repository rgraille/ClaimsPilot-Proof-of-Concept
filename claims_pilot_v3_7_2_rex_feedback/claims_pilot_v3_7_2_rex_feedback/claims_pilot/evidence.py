from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime

from .extractor import ExtractedFacts
from .visual import visual_supports_materiality, visual_has_safety_risk


@dataclass
class EvidenceItem:
    code: str
    label: str
    status: str  # RECU / OBJECTIVE / MANQUANT / A_VERIFIER / NON_APPLICABLE
    confidence: int
    source: str
    detail: str
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceAssessment:
    items: List[EvidenceItem]
    received: List[str]
    missing: List[str]
    to_verify: List[str]
    auto_options: Dict[str, bool]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "received": self.received,
            "missing": self.missing,
            "to_verify": self.to_verify,
            "auto_options": self.auto_options,
        }



DATE_RE_EVIDENCE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

def _parse_date_evidence(s: str):
    if not s:
        return None
    m = DATE_RE_EVIDENCE.search(s)
    if not m:
        return None
    d, mo, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        return datetime(int(y), int(mo), int(d))
    except ValueError:
        return None

def _years_since_reception_evidence(facts: ExtractedFacts):
    d1 = _parse_date_evidence(getattr(facts, "reception_date", ""))
    d2 = _parse_date_evidence(getattr(facts, "declaration_date", "")) or _parse_date_evidence(getattr(facts, "loss_date", "")) or datetime.today()
    if not d1 or not d2:
        return None
    return max(0.0, (d2 - d1).days / 365.25)

def _find_snippet(text: str, patterns: List[str], window: int = 180) -> str:
    low = text.lower()
    for p in patterns:
        m = re.search(p, low, flags=re.I)
        if m:
            start = max(0, m.start() - window // 2)
            end = min(len(text), m.end() + window // 2)
            return re.sub(r"\s+", " ", text[start:end]).strip()[:360]
    return ""


def _has_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)


def _add(items: List[EvidenceItem], code: str, label: str, status: str, confidence: int, source: str, detail: str, snippet: str = "") -> None:
    items.append(EvidenceItem(code=code, label=label, status=status, confidence=max(0, min(100, confidence)), source=source, detail=detail, snippet=snippet))


def assess_evidence(facts: ExtractedFacts, raw_text: str, file_summaries: Optional[List[Dict[str, Any]]] = None) -> EvidenceAssessment:
    """Analyse automatiquement les éléments reçus et les éléments manquants.

    L'objectif n'est pas de transformer une déclaration en preuve définitive, mais de
    distinguer :
    - ce qui est reçu dans le dossier,
    - ce qui est objectivé par une pièce/mesure/rapport,
    - ce qui reste à obtenir pour fiabiliser la position.
    """
    file_summaries = file_summaries or []
    txt = raw_text or ""
    low = txt.lower()
    items: List[EvidenceItem] = []

    uploaded_names = [str(f.get("name", "")) for f in file_summaries]
    uploaded_joined = " ".join(uploaded_names).lower()
    image_findings = []
    for f in file_summaries:
        for im in f.get("images", []) or []:
            try:
                from .visual import ImageFinding
                image_findings.append(ImageFinding(**im))
            except Exception:
                pass
    visual_materiality = visual_supports_materiality(image_findings)
    visual_safety = visual_has_safety_risk(image_findings)
    exploitable_images = [im for im in image_findings if im.status in {"EXPLOITABLE", "PARTIEL"}]

    # 1. Pièces et éléments administratifs
    if facts.declared_damage:
        _add(items, "DECLARATION_DOMMAGE", "Dommage déclaré", "RECU", 90, "déclaration", "Un libellé de dommage a été extrait.", facts.declared_damage[:360])
    else:
        _add(items, "DECLARATION_DOMMAGE", "Dommage déclaré", "MANQUANT", 0, "dossier", "Aucun libellé de dommage exploitable n'a été extrait.")

    if facts.reception_date:
        _add(items, "DATE_RECEPTION", "Date de réception", "RECU", 95, "déclaration / pièces", f"Date extraite : {facts.reception_date}", _find_snippet(txt, [r"réception", r"reception"]))
    else:
        _add(items, "DATE_RECEPTION", "Date de réception", "MANQUANT", 0, "dossier", "La date de réception est nécessaire pour situer le sinistre dans la décennale et appliquer les règles GPA/TM/TVA.")

    if facts.declaration_date or facts.loss_date:
        _add(items, "DATE_SINISTRE_DECLARATION", "Date de sinistre / déclaration", "RECU", 90, "déclaration / email", f"Date extraite : {facts.loss_date or facts.declaration_date}", _find_snippet(txt, [r"date du sinistre", r"déclar", r"declar", r"survenu"]))
    else:
        _add(items, "DATE_SINISTRE_DECLARATION", "Date de sinistre / déclaration", "MANQUANT", 0, "dossier", "Il faut une date de survenance ou de déclaration pour apprécier prescription, année après réception et urgence.")

    if facts.construction_type != "Non déterminé":
        _add(items, "TYPE_OUVRAGE", "Type d'ouvrage", "RECU", 80, "déclaration", facts.construction_type, _find_snippet(txt, [r"appartement", r"bâtiment collectif", r"batiment collectif", r"maison", r"logement", r"commerce"]))
    else:
        _add(items, "TYPE_OUVRAGE", "Type d'ouvrage", "A_VERIFIER", 30, "dossier", "Le type d'ouvrage n'est pas déterminé ; il influence l'analyse technique, la TVA et l'usage attendu.")

    if facts.location != "Non déterminé":
        _add(items, "LOCALISATION", "Localisation du désordre", "RECU", 85, "déclaration", facts.location, _find_snippet(txt, [r"salle de bain", r"douche", r"parking", r"sous-sol", r"façade", r"facade", r"balcon", r"terrasse"]))
    else:
        _add(items, "LOCALISATION", "Localisation du désordre", "MANQUANT", 0, "dossier", "La localisation précise est nécessaire pour rattacher le symptôme à l'ouvrage et aux fiches pathologie.")

    # 2. Photos / pièces visuelles
    photo_from_filename = any(("photo" in n or n.endswith(('.jpg', '.jpeg', '.png', '.heic'))) for n in uploaded_names)
    photo_from_text = facts.has_photos or _has_any(low, [r"photos? (?:jointes?|associées?|transmises?)", r"pi[èe]ces? jointes?", r"image"])
    if exploitable_images:
        details = []
        for im in exploitable_images[:3]:
            details.append(f"{im.image_name} : {im.technical_note[:220]}")
        _add(items, "PHOTOS", "Photos ou pièces visuelles", "OBJECTIVE", 85, "analyse visuelle", "Des photos ont été analysées automatiquement et sont exploitables pour une lecture de premier niveau.", " | ".join(details))
    elif photo_from_filename or photo_from_text or image_findings:
        source = "pièce jointe" if photo_from_filename or image_findings else "déclaration"
        _add(items, "PHOTOS", "Photos ou pièces visuelles", "RECU", 65 if image_findings else 55, source, "Des photos ou pièces visuelles sont mentionnées ou déposées ; leur exploitabilité est partielle ou à vérifier.", "; ".join(uploaded_names[:5]) or _find_snippet(txt, [r"photo", r"pi[èe]ce jointe", r"image"]))
    else:
        _add(items, "PHOTOS", "Photos ou pièces visuelles", "MANQUANT", 0, "dossier", "Photos générales et rapprochées du désordre à demander.")

    # 3. Objectivation de la matérialité
    expert_constat = _has_any(low, [
        r"je constate", r"nous constatons" if "rapport" in low else r"a^", r"constat de la matérialité.*oui", r"matérialité.*oui",
        r"l.expert.*constat", r"test[s]? .*indiqu", r"humidim[èe]tre", r"mesur[ée]", r"test d.arrosage", r"mise en eau", r"recherche de fuite"
    ])
    declaration_constat = _has_any(low, [r"nous constatons", r"je constate", r"apparition", r"présence de", r"presence de"])
    if expert_constat:
        _add(items, "MATERIALITE", "Matérialité du dommage", "OBJECTIVE", 90, "rapport / mesure", "La matérialité paraît objectivée par un constat, une mesure ou un test.", _find_snippet(txt, [r"je constate", r"constat de la matérialité", r"humidim[èe]tre", r"test", r"mesur"]))
    elif visual_materiality:
        _add(items, "MATERIALITE", "Matérialité du dommage", "OBJECTIVE", 78, "analyse visuelle", "La photo permet d'objectiver visuellement un désordre apparent, sous réserve de validation experte.", _find_snippet(txt, [r"analyse visuelle", r"suspension", r"plafond", r"chute", r"photo"]))
    elif declaration_constat or photo_from_filename or photo_from_text:
        _add(items, "MATERIALITE", "Matérialité du dommage", "A_VERIFIER", 55, "déclaration / photos", "Le symptôme est allégué ou illustré, mais il n'est pas encore objectivé par un constat technique mesuré ou une photo exploitable.", _find_snippet(txt, [r"nous constatons", r"apparition", r"présence de", r"photo"]))
    else:
        _add(items, "MATERIALITE", "Matérialité du dommage", "MANQUANT", 0, "dossier", "La matérialité du dommage doit être objectivée.")

    # 4. Symptôme eau / humidité / fuite
    humidity_measure = _has_any(low, [r"humidim[èe]tre", r"humidité active", r"humidite active", r"\d{2,3}/100\s*digits", r"taux d.humidit", r"mesure d.humidit"])
    active_leak = _has_any(low, [r"fuite active", r"écoulement", r"ecoulement", r"test d.arrosage", r"mise en eau", r"reproduit", r"reproduction de la fuite"])
    if humidity_measure or active_leak:
        _add(items, "EAU_HUMIDITE", "Humidité / fuite objectivée", "OBJECTIVE", 95, "mesure / test", "Le dossier contient une mesure d'humidité ou un test reproduisant l'écoulement.", _find_snippet(txt, [r"humidim[èe]tre", r"humidité active", r"\d{2,3}/100", r"test d.arrosage", r"écoulement", r"reproduit"]))
    elif getattr(facts, "mentions_mold_condensation", False):
        _add(items, "EAU_HUMIDITE", "Moisissures / condensation", "RECU", 70, "déclaration / photos", "Le dossier mentionne des moisissures ponctuelles ; à ce stade, il faut surtout distinguer condensation/ventilation d'une humidité active ou d'une infiltration.", _find_snippet(txt, [r"moisiss", r"condensation", r"chambre", r"photo"]))
    elif facts.mentions_humidity_or_water:
        _add(items, "EAU_HUMIDITE", "Humidité / fuite", "RECU", 65, "déclaration", "Le dossier mentionne une humidité, une infiltration ou une fuite ; une mesure ou un test peut être nécessaire.", _find_snippet(txt, [r"humid", r"fuite", r"infiltration", r"eau", r"tache"]))
    else:
        _add(items, "EAU_HUMIDITE", "Humidité / fuite", "NON_APPLICABLE", 50, "analyse", "Aucun indice d'eau ou d'humidité n'est détecté.")

    # 4bis. Risque sécurité / chute
    if visual_safety or (facts.mentions_safety and facts.mentions_ceiling_suspension):
        _add(items, "RISQUE_SECURITE", "Risque sécurité / chute", "OBJECTIVE" if visual_safety else "A_VERIFIER", 85 if visual_safety else 65, "déclaration / photos", "Le dossier vise un élément en plafond ou une suspension susceptible de tomber ; la mesure conservatoire et la vérification du support sont prioritaires.", _find_snippet(txt, [r"suspension", r"faux plafond", r"menace de tomber", r"sécurité", r"chute"]))
    elif facts.mentions_safety:
        _add(items, "RISQUE_SECURITE", "Risque sécurité", "A_VERIFIER", 60, "déclaration", "Un risque de sécurité est allégué ; il doit être objectivé par photo, constat ou mesure.", _find_snippet(txt, [r"sécurité", r"danger", r"chute", r"risque"]))

    # 5. Cause étrangère / entretien / usage
    # Règle V2.2 : on n'invoque pas une cause étrangère abstraite. Elle n'est affichée
    # que si le dossier contient un indice concret ou si une fiche entretien applicable est croisée.
    if _has_any(low, [r"aucune cause étrangère", r"aucun défaut d.entretien", r"entretien.*écart", r"cause étrangère.*écart"]):
        _add(items, "CAUSE_ETRANGERE", "Cause étrangère / entretien", "NON_APPLICABLE", 80, "déclaration / rapport", "Aucune cause étrangère concrète n'est identifiée dans les éléments reçus ; ne pas l'invoquer dans la réponse.", _find_snippet(txt, [r"aucune cause", r"défaut d.entretien", r"cause étrangère"]))
    elif getattr(facts, "mentions_characterized_maintenance_defect", False) or getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        years = _years_since_reception_evidence(facts)
        if getattr(facts, "mentions_shower_mastic_maintenance_defect", False) and years is not None and years < 2.0:
            detail = "Infiltration périphérique de receveur dans les deux premières années : ne pas objectiver un défaut d'entretien ; rechercher un défaut constructif de calage du receveur ou de barrières d'étanchéité."
            _add(items, "CAUSE_ETRANGERE", "Défaut d'entretien non retenu à ce stade", "A_VERIFIER", 55, "analyse", detail, _find_snippet(txt, [r"receveur", r"mastic", r"joint", r"périph", r"pied de cloison"]))
        else:
            detail = "Le dossier rattache le désordre à une fiche entretien et à un défaut concret : le défaut d'entretien peut être invoqué, en le nommant précisément."
            if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
                detail = "Le dossier rattache l'infiltration en périphérie du receveur au maintien en bon état d'usage des mastics souples : défaut d'entretien caractérisé."
            _add(items, "CAUSE_ETRANGERE", "Défaut d'entretien caractérisé", "OBJECTIVE", 85, "déclaration / fiche entretien", detail, _find_snippet(txt, [r"mainteneur", r"relev", r"étanch", r"devis", r"entretien", r"toiture", r"receveur", r"mastic", r"joint", r"périph"]))
    elif facts.mentions_maintenance:
        _add(items, "CAUSE_ETRANGERE", "Cause étrangère / entretien", "A_VERIFIER", 45, "déclaration", "Indice concret d'entretien, usage, usure ou maintenance présent : la cause étrangère peut seulement être listée comme point à vérifier et doit être nommée.", _find_snippet(txt, [r"entretien", r"maintenance", r"usure", r"usage", r"nettoyage", r"obstru", r"bouch"] ))
    else:
        _add(items, "CAUSE_ETRANGERE", "Cause étrangère", "NON_APPLICABLE", 70, "analyse", "Aucune cause étrangère pertinente n'est détectée ; aucune CE ne doit être invoquée.")

    # 6. Chiffrage / devis
    if facts.cost_ttc is not None:
        status = "RECU" if facts.has_quote else "A_VERIFIER"
        conf = 80 if facts.has_quote else 60
        _add(items, "CHIFFRAGE", "Chiffrage / devis", status, conf, "déclaration / pièce", f"Montant identifié : {facts.cost_ttc:.2f} € TTC. Vérifier s'il s'agit d'un devis, d'une estimation ou d'un montant expert.", _find_snippet(txt, [r"devis", r"montant", r"quantum", r"chiffrage", r"€", r"euros"]))
    elif getattr(facts, "mentions_mold_condensation", False):
        _add(items, "CHIFFRAGE", "Chiffrage / devis", "NON_APPLICABLE", 70, "analyse", "Pas de chiffrage réparatoire décennal attendu si les moisissures restent ponctuelles et relèvent du nettoyage/entretien ventilation.")
    elif getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        years = _years_since_reception_evidence(facts)
        if years is not None and years < 2.0:
            _add(items, "CHIFFRAGE", "Chiffrage / devis", "MANQUANT", 0, "dossier", "Chiffrage utile si l'origine constructive est confirmée : reprise du calage/receveur, joints et parements affectés.")
        else:
            _add(items, "CHIFFRAGE", "Chiffrage / devis", "NON_APPLICABLE", 70, "analyse", "Pas de chiffrage réparatoire décennal attendu si l'orientation retenue est l'entretien localisé des mastics périphériques du receveur.")
    else:
        _add(items, "CHIFFRAGE", "Chiffrage / devis", "MANQUANT", 0, "dossier", "Devis, quantités ou estimation de réparation à obtenir pour statuer sur G<TM.")

    # 7. Réserve / GPA / travaux non terminés
    if facts.mentions_reserve_or_gpa:
        _add(items, "RESERVE_GPA", "Réserve / GPA / travaux non terminés", "RECU", 75, "déclaration / rapport", "Des indices de réserve, GPA ou travaux non terminés sont présents ; ils peuvent orienter vers une non-garantie si aucune gravité décennale n'est objectivée.", _find_snippet(txt, [r"réserve", r"reserve", r"gpa", r"parfait ach", r"travaux non termin", r"terminer"]))
    else:
        _add(items, "RESERVE_GPA", "Réserve / GPA / travaux non terminés", "NON_APPLICABLE", 50, "analyse", "Aucun indice de réserve, GPA ou travaux non terminés n'est détecté dans le libellé du sinistre.")

    materiality_objective = any(i.code == "MATERIALITE" and i.status == "OBJECTIVE" for i in items)
    materiality_partial = any(i.code == "MATERIALITE" and i.status in {"OBJECTIVE", "A_VERIFIER"} for i in items)
    water_objective = any(i.code == "EAU_HUMIDITE" and i.status == "OBJECTIVE" for i in items)
    photos_received = any(i.code == "PHOTOS" and i.status in {"RECU", "OBJECTIVE"} for i in items)
    quote_received = any(i.code == "CHIFFRAGE" and i.status in {"RECU", "A_VERIFIER"} for i in items)
    maintenance_neutralized = _has_any(low, [r"aucune cause étrangère", r"aucun défaut d.entretien", r"entretien.*écart", r"cause étrangère.*écart"])

    auto_options = {
        "materiality_observed": materiality_objective,
        "materiality_partial": materiality_partial,
        "photos_exploitable": photos_received,
        "humidity_measured": humidity_measure,
        "active_leak": active_leak,
        "quote_available": quote_received,
        "maintenance_neutralized": maintenance_neutralized,
        "senior_sensitive": bool(visual_safety or facts.mentions_solidite),
        "visual_safety": bool(visual_safety),
        "visual_materiality": bool(visual_materiality),
    }

    received = [f"{i.label} : {i.detail}" for i in items if i.status in {"RECU", "OBJECTIVE"}]
    missing = [f"{i.label} : {i.detail}" for i in items if i.status == "MANQUANT"]
    to_verify = [f"{i.label} : {i.detail}" for i in items if i.status == "A_VERIFIER"]

    return EvidenceAssessment(items=items, received=received, missing=missing, to_verify=to_verify, auto_options=auto_options)
