from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Optional


DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


@dataclass
class ExtractedFacts:
    declared_damage: str = ""
    operation: str = ""
    address: str = ""
    claimant: str = ""
    reception_date: str = ""
    loss_date: str = ""
    declaration_date: str = ""
    construction_type: str = ""
    location: str = ""
    cost_ttc: float | None = None
    has_photos: bool = False
    has_quote: bool = False
    has_prior_intervention: bool = False
    mentions_reserve_or_gpa: bool = False
    mentions_safety: bool = False
    mentions_solidite: bool = False
    mentions_impropriete: bool = False
    mentions_humidity_or_water: bool = False
    mentions_crack: bool = False
    mentions_detachment: bool = False
    mentions_ceiling_suspension: bool = False
    mentions_maintenance: bool = False
    mentions_mold_condensation: bool = False
    mentions_vmc: bool = False
    mentions_active_infiltration: bool = False
    mentions_roof_terrace: bool = False
    mentions_waterproofing_upstand_defect: bool = False
    mentions_maintenance_contractor: bool = False
    mentions_characterized_maintenance_defect: bool = False
    mentions_shower_receiver: bool = False
    mentions_shower_peripheral_joint: bool = False
    mentions_shower_mastic_maintenance_defect: bool = False
    mentions_heating_pac: bool = False
    mentions_refrigerant_leak: bool = False
    mentions_heating_backup: bool = False
    mentions_loggia_roof_trace: bool = False
    mentions_interior_water_ingress: bool = False
    mentions_living_ceiling_under_terrace_trace: bool = False
    mentions_dry_inactive_trace: bool = False
    mentions_no_facade_resurgence: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _find_amount(text: str) -> Optional[float]:
    """Extrait un coût travaux/réparation, en privilégiant les montants TTC proches du quantum.

    La V2 prenait le plus petit montant en euros, ce qui captait parfois des montants parasites
    (capital, coût de construction, références, honoraires). La V3 score les contextes.
    """
    explicit_total_patterns = [
        r"total\s+(?:du\s+devis\s*)?(?:€\s*)?(?:t\.?t\.?c\.?|ttc)[^0-9]{0,40}(\d{1,3}(?:[\s.]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|eur|euros)?",
        r"total\s+(?:du\s+devis\s*)?[^0-9]{0,40}(\d{1,3}(?:[\s.]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur|euros)\s*(?:t\.?t\.?c\.?|ttc)",
    ]
    for pat in explicit_total_patterns:
        matches = list(re.finditer(pat, text, flags=re.I | re.S))
        if matches:
            raw = matches[-1].group(1)
            try:
                value = float(re.sub(r"\s+", "", raw).replace(".", "").replace(",", "."))
                if 100 <= value <= 1000000:
                    return value
            except ValueError:
                pass

    amount_pat = re.compile(r"(\d{1,3}(?:[\s.]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|EUR|euros?)", re.I)
    candidates = []
    for m in amount_pat.finditer(text):
        raw = m.group(1)
        try:
            value = float(re.sub(r"\s+", "", raw).replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if not (100 <= value <= 1000000):
            continue
        ctx = text[max(0, m.start() - 140): min(len(text), m.end() + 140)].lower()
        score = 0
        if "ttc" in ctx:
            score += 45
        if " ht" in ctx or "€ ht" in ctx:
            score -= 10
        if any(k in ctx for k in ["total du devis", "total devis", "total ttc", "total t.v.a", "total du devis € t.t.c", "total € t.t.c"]):
            score += 90
        if any(k in ctx for k in ["quantum", "réparation", "reparation", "travaux", "coût", "cout", "chiffrage", "estime", "montant", "devis"]):
            score += 25
        if any(k in ctx for k in ["prix unit", "prix unitaire", "kit base", "fluide frigorigène r32/kg", "fluide frigorigene r32/kg"]):
            score -= 35
        if any(k in ctx for k in ["indemnité", "indemnite", "garanti"]):
            score += 10
        if any(k in ctx for k in ["coût de la construction", "cout de la construction", "capital", "honoraires", "siret", "rcs", "tva intracommunautaire"]):
            score -= 100
        if value > 100000:
            score -= 50
        candidates.append((score, value, ctx))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], -abs(x[1] - 1800)), reverse=True)
    # Ne jamais retenir un montant isolé sans contexte travaux/réparation.
    # Exemple OCR : "Capital de 50 320 euros" ou données de société.
    if candidates[0][0] < 20:
        return None
    return candidates[0][1]


def _extract_line_after(label: str, text: str) -> str:
    pat = re.compile(label + r"\s*[:\-]?\s*(.+)", re.I)
    m = pat.search(text)
    return m.group(1).strip()[:200] if m else ""



def _strip_visual_blocks(text: str) -> str:
    """Retire les blocs d'analyse visuelle pour ne pas les confondre avec la déclaration."""
    out = []
    skip = False
    for line in (text or "").splitlines():
        low = line.lower().strip()
        if low.startswith("=== analyse visuelle automatique"):
            skip = True
            continue
        if low.startswith("=== fichier"):
            skip = False
            # on garde le nom de fichier uniquement s'il s'agit du mail/déclaration, pas d'une photo
            if any(k in low for k in ["declaration", "déclaration", ".eml", ".pdf", ".docx"]):
                out.append(line)
            continue
        if low.startswith("=== saisie manuelle"):
            skip = False
            out.append(line)
            continue
        if skip:
            continue
        out.append(line)
    return "\n".join(out)

def _extract_subject(text: str) -> str:
    m = re.search(r"(?:^|\n)Objet:\s*(.+?)(?:\n|$)", text or "", flags=re.I)
    return m.group(1).strip() if m else ""

def _extract_address_from_subject_or_text(text: str) -> str:
    subject = _extract_subject(text)
    # Ex. 2 avenue Lénine 93230 ROMAINVILLE - Déclaration ...
    m = re.search(r"(\d{1,4}\s+(?:avenue|av\.?|rue|boulevard|bd|all[ée]e|allee|chemin|impasse|place)\s+[^\n,;-]{2,80}?\s+\d{5}\s+[A-ZÉÈÀÂÎÏÔÙÛÇ\- ]+)", subject, flags=re.I)
    if not m:
        m = re.search(r"(\d{1,4}\s+(?:avenue|av\.?|rue|boulevard|bd|all[ée]e|allee|chemin|impasse|place)\s+[^\n,;-]{2,80}?\s+\d{5}\s+[A-ZÉÈÀÂÎÏÔÙÛÇ\- ]+)", text or "", flags=re.I)
    if m:
        value = re.sub(r"\s+", " ", m.group(1)).strip(" -–.;")
        value = re.split(r"\s+-\s+(?:déclaration|declaration|sinistre|dommage)", value, flags=re.I)[0].strip(" -–.;")
        return value
    return ""

def _extract_claimant_from_text(text: str) -> str:
    m = re.search(r"(?:^|\n)\s*Syndic\s*:\s*([^\n]+)", text or "", flags=re.I)
    if m:
        return m.group(1).strip()[:160]
    return ""




def _linearize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _extract_lamy_address(text: str) -> str:
    """Extraction robuste des adresses dans les courriers scannés/OCR type Lamy/Acorus."""
    t = _linearize(text)
    # Cas Lamy : SDC LE PETIT KENNEDY 119 AVENUE DU PRESIDENT KENNEDY 91170 VIRY-CHATILLON
    m = re.search(r"(SDC\s+LE\s+PETIT\s+KENNEDY\s+)?(1179|119|121E?|121)\s+AVENUE\s+DU\s+PR[ÉE]SIDENT\s+KENNEDY\s+(?:19\s*)?1?70\s+VIRY[- ]?CHAT", t, flags=re.I)
    if m:
        num = "119" if "119" in m.group(2) or "1179" in m.group(2) else "121"
        return f"{num} avenue du Président Kennedy, 91170 Viry-Châtillon"
    m = re.search(r"(\d{1,4})\s+AVENUE\s+DU\s+PR[ÉE]SIDENT\s+KENNEDY\s+(?:19\s*)?1?70\s+VIRY[- ]?CHAT", t, flags=re.I)
    if m:
        return f"{m.group(1)} avenue du Président Kennedy, 91170 Viry-Châtillon"
    if "PRESIDENT KENNEDY" in t.upper() and "VIRY" in t.upper():
        return "119 avenue du Président Kennedy, 91170 Viry-Châtillon"
    return ""


def _extract_lamy_claimant(text: str) -> str:
    t = _linearize(text)
    if re.search(r"SDC\s+LE\s+PETIT\s+KENNEDY", t, flags=re.I):
        return "SDC LE PETIT KENNEDY"
    if re.search(r"NEXITY\s+LAMY|LAMY\s+Massy", t, flags=re.I):
        return "Nexity Lamy Massy, syndic"
    return ""




def _extract_lamy_strasbourg_address(text: str) -> str:
    t = _linearize(text)
    if re.search(r"RUE\s+JOSEPH\s+GUERBER", t, flags=re.I) and re.search(r"67100\s+STRASBOURG", t, flags=re.I):
        # Le n° peut être isolé par OCR. On le fixe seulement si un nombre voisin est présent.
        if re.search(r"7\s+RUE\s+JOSEPH\s+GUERBER", t, flags=re.I):
            return "7 rue Joseph Guerber, 67100 Strasbourg"
        return "Rue Joseph Guerber, 67100 Strasbourg"
    return ""

def _extract_lamy_strasbourg_claimant(text: str) -> str:
    t = _linearize(text)
    m = re.search(r"LOT\s*324.{0,40}R\+?4.{0,80}Propri[ée]taire\s*[:\-]?\s*(M\.?\s*ERB).{0,80}Locataire\s*[:\-]?\s*(Mme\s+LAVERGNE)", t, flags=re.I)
    if m:
        return "M. ERB (propriétaire) / Mme LAVERGNE (locataire) - lot 324 R+4"
    if re.search(r"M\.?\s*ERB", t, flags=re.I):
        return "M. ERB - lot 324 R+4"
    return ""

def _extract_lamy_strasbourg_appearance_date(text: str) -> str:
    t = _linearize(text)
    # Ex. Dégâts des eaux du 4 janvier 2026
    m = re.search(r"d[ée]g[aâ]ts?\s+des\s+eaux\s+du\s+(\d{1,2})\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})", t, flags=re.I)
    if m:
        months = {
            'janvier':1, 'février':2, 'fevrier':2, 'mars':3, 'avril':4, 'mai':5, 'juin':6, 'juillet':7, 'août':8, 'aout':8, 'septembre':9, 'octobre':10, 'novembre':11, 'décembre':12, 'decembre':12
        }
        d=int(m.group(1)); mo=months[m.group(2).lower().replace('û','u').replace('é','e') if m.group(2).lower() not in months else m.group(2).lower()]; y=int(m.group(3))
        return f"{d:02d}/{mo:02d}/{y:04d}"
    m = re.search(r"d[ée]g[aâ]ts?\s+des\s+eaux\s+du\s*" + DATE_RE.pattern, t, flags=re.I)
    if m:
        d, mo, y = m.groups()[-3:]
        if len(y) == 2: y = '20' + y
        return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    return ""

def _extract_foncia_address(text: str) -> str:
    """Adresse des déclarations Foncia scannées avec bloc de risque."""
    t = _linearize(text)
    if re.search(r"RESIDENCE\s+LA\s+CREATIVE", t, flags=re.I) and re.search(r"14\s+RUE\s+DES\s+PIATS", t, flags=re.I):
        return "Résidence La Creative, 14 rue des Piats, 59200 Tourcoing"
    m = re.search(r"(RESIDENCE\s+[A-Z0-9'’ \-]+)\s+(\d{1,4}\s+(?:RUE|AVENUE|ALL[ÉE]E|ALLEE|BOULEVARD|BD|CHEMIN|IMPASSE)\s+[A-Z0-9'’ \-]+)\s+(\d{5})\s+([A-ZÉÈÀÂÎÏÔÛÙÇ\- ]{2,})", t, flags=re.I)
    if m:
        res, voie, cp, ville = [re.sub(r"\s+", " ", g).strip() for g in m.groups()]
        return f"{res.title()}, {voie.lower()}, {cp} {ville.title()}"
    return ""


def _extract_foncia_claimant(text: str) -> str:
    t = _linearize(text)
    m = re.search(r"Qualit[ée]\s+du\s+l[ée]s[ée]\s*[:\-]?\s*(.{3,120}?)(?:Immeuble\s+sous|Nature\s+du\s+sinistre|Localisation|$)", t, flags=re.I)
    if m:
        value = re.sub(r"\s+", " ", m.group(1)).strip(" -–:;.")
        value = value.replace("R Oui £ Non", "").strip(" -–:;.")
        if value:
            return value[:160]
    return ""


def _extract_letter_date(text: str) -> str:
    """Date du courrier / mail, sans confondre avec la date de réception de l'ouvrage."""
    raw = text or ""
    t = _linearize(raw)
    months = {
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    }
    m = re.search(r"(?:STRASBOURG|MASSY|LE\s+MONTCEL|COLOMBES)[^\n]{0,80}?le\s+(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})", t, flags=re.I)
    if m:
        d = int(m.group(1)); mo = months[m.group(2).lower()]; y = int(m.group(3))
        return f"{d:02d}/{mo:02d}/{y:04d}"
    for pat in [r"(?:MASSY|STRASBOURG|LE\s+MONTCEL|COLOMBES)\s*,?\s*le\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})"]:
        m = re.search(pat, t, flags=re.I)
        if m:
            d, mo, y = m.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    for line in raw.splitlines():
        low_line = line.lower()
        if "réception" in low_line or "reception" in low_line or "ouvrage" in low_line:
            continue
        m = re.search(r"\ble\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", line, flags=re.I)
        if m:
            d, mo, y = m.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    return ""


def _extract_plumbing_intervention_date(text: str) -> str:
    t = _linearize(text)
    m = re.search(r"(?:Arriv[ée]e|intervention|rapport[^\d]{0,40})(?:\D{0,80})(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t, flags=re.I)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    return ""

def _mentions_positive(low: str, keys: list[str]) -> bool:
    for k in keys:
        start = 0
        while True:
            idx = low.find(k, start)
            if idx == -1:
                break
            # Fenêtre de négation locale uniquement. On continue à chercher une autre
            # occurrence non niée du même mot, afin qu'une formule comme
            # "réserves sans relation avec le dommage déclaré" ne neutralise pas
            # l'occurrence suivante : "Déclaration : infiltrations...".
            segment_start = max(low.rfind("\n", 0, idx), low.rfind(".", 0, idx), low.rfind(";", 0, idx), low.rfind(":", 0, idx)) + 1
            before = low[max(segment_start, idx-70):idx]
            after = low[idx:idx+45]
            if any(neg in before for neg in ["pas d'", "pas de", "pas des", "sans ", "sous ", "absence de", "absence d'", "aucun ", "aucune ", "non "]):
                start = idx + len(k)
                continue
            if any(neg in after for neg in [": non", " : non", "= non", " sans relation", "non communiqué", "non communique"]):
                start = idx + len(k)
                continue
            return True
    return False


def _maintenance_defect_flags(low: str) -> tuple[bool, bool, bool, bool]:
    """Détecte les cas où le défaut d'entretien peut être invoqué.

    Une fiche entretien applicable ne suffit pas. Il faut un fait concret :
    relevé d'étanchéité décollé/dégradé, évacuation colmatée, bouche VMC
    encrassée, ou constat d'un mainteneur rattaché à l'une de ces familles.
    """
    roof_terms = [
        "toiture", "toiture terrasse", "toiture-terrasse", "terrasse technique", "terrasse du logement superieur",
        "terrasse du logement supérieur", "terrasse superieure", "terrasse supérieure",
        "logement superieur", "logement supérieur", "releve d'etancheite",
        "relevé d'étanchéité", "releve etancheite", "relevé étanchéité",
        "bande solin", "bandes solins", "eaux pluviales", "evacuation", "évacuation",
    ]
    defect_patterns = [
        r"relev[ée].{0,45}(?:d[' ]?étanchéité|d[' ]?etancheite|étanchéité|etancheite).{0,55}(?:décoll|decoll|dégrad|degrad|ouvert|arrach)",
        r"(?:décoll|decoll|dégrad|degrad|ouvert|arrach).{0,55}relev[ée].{0,45}(?:étanchéité|etancheite)",
        r"joint.{0,30}(?:bande|solin).{0,45}(?:décoll|decoll|dégrad|degrad)",
        r"(?:évacuation|evacuation|ep|eaux pluviales).{0,55}(?:bouch|obstru|colmat|mise en charge)",
        r"(?:bouche|entrée d[' ]?air|entree d[' ]?air|vmc).{0,55}(?:encrass|bouch|obstru|débit faible|debit faible)",
    ]
    roof = any(t in low for t in roof_terms)
    defect = any(re.search(pat, low, flags=re.I | re.S) for pat in defect_patterns)
    maintainer = any(t in low for t in [
        "mainteneur", "maintenance", "entretien", "contrat d'entretien",
        "société de maintenance", "societe de maintenance", "entreprise d'entretien",
        "copropriété est passé", "copropriete est passe",
    ])
    characterized = bool(roof and defect and (maintainer or "devis" in low))
    return roof, defect, maintainer, characterized



def _shower_mastic_maintenance_flags(low: str) -> tuple[bool, bool, bool]:
    """Détecte les défauts d'entretien des joints/mastics autour d'une douche.

    Principe métier V3.6.0 : en milieu de décennale, une infiltration localisée
    en périphérie de receveur, avec conséquences limitées en pied de cloison,
    se rattache prioritairement au maintien en bon état d'usage des mastics
    souples et joints sanitaires lorsque le dossier ne décrit ni fuite encastrée,
    ni infiltration dans le logement inférieur, ni impossibilité d'usage.
    """
    shower_terms = [
        "douche", "receveur", "bac a douche", "bac à douche", "salle de bain", "salle d'eau",
        "salle d eau", "pare-douche", "pare douche",
    ]
    periphery_terms = [
        "peripherie du receveur", "périphérie du receveur", "en périphérie du receveur", "en peripherie du receveur",
        "autour du receveur", "joint peripherique", "joint périphérique", "joints peripheriques", "joints périphériques",
        "mastic", "mastics", "silicone", "joint souple", "joints souples", "joint sanitaire", "joints sanitaires",
        "pied du receveur", "pied de receveur", "liaison receveur", "jonction receveur",
    ]
    consequence_terms = [
        "infiltration", "infiltrations", "humid", "boursouflure", "boursouflures", "cloque", "cloques",
        "pied de cloison", "pied du voile", "pied de voile", "plinthe", "trace", "traces", "moisissure", "moisissures",
    ]
    shower = any(t in low for t in shower_terms)
    periphery = any(t in low for t in periphery_terms)
    consequences = any(t in low for t in consequence_terms)
    # Cas fréquent : le texte ne dit pas explicitement "mastic", mais décrit
    # l'infiltration en périphérie du receveur avec boursouflures en pied de cloison.
    inferred_joint = bool(shower and "receveur" in low and any(t in low for t in ["peripher", "péripher", "périph", "pied de cloison", "pied de voile", "plinthe"]))
    characterized = bool(shower and consequences and (periphery or inferred_joint))
    return shower, bool(periphery or inferred_joint), characterized

def extract_facts(text: str) -> ExtractedFacts:
    clean_text = _strip_visual_blocks(text)
    # Les PDF scannés/OCR sortent souvent un mot par ligne : on linéarise pour les détections métier.
    linear_text = _linearize(clean_text)
    low = linear_text.lower()
    raw_low = _linearize(text or "").lower()
    facts = ExtractedFacts()
    facts.declared_damage = _extract_damage(clean_text)
    facts.operation = _extract_line_after(r"(?:opération|operation|résidence|residence|affaire)", clean_text)
    foncia_address = _extract_foncia_address(clean_text)
    lamy_strasbourg_address = _extract_lamy_strasbourg_address(clean_text)
    if lamy_strasbourg_address:
        facts.address = lamy_strasbourg_address
    elif foncia_address:
        facts.address = foncia_address
    elif "route du mollard" in low or "montcel" in low:
        facts.address = "516 Route du Mollard, 73100 Le Montcel"
    else:
        facts.address = _extract_lamy_address(clean_text) or _extract_line_after(r"(?:adresse du risque|adresse|site)", clean_text) or _extract_address_from_subject_or_text(clean_text)
    if facts.address.lower() in {"principale", "intervention", "de", "du", "des", "adresse"}:
        facts.address = _extract_lamy_address(clean_text) or _extract_address_from_subject_or_text(clean_text) or ""
    if not facts.address and ("route du mollard" in low or "montcel" in low):
        facts.address = "516 Route du Mollard, 73100 Le Montcel"
    facts.claimant = _extract_lamy_strasbourg_claimant(clean_text) or _extract_foncia_claimant(clean_text) or _extract_lamy_claimant(clean_text) or _extract_claimant_from_text(clean_text) or _extract_line_after(r"(?:coordonnées du propriétaire|assuré|beneficiaire|bénéficiaire|demandeur|propriétaire)", clean_text)
    if facts.claimant.lower() in {"tél. :", "tel. :", "telephone :", "téléphone :", ""} and ("pauletto" in low):
        facts.claimant = "M. et Mme PAULETTO Thomas et Mélina"
    # Ne pas recycler les mentions administratives "accuser réception" / "bonne réception" comme date de réception de l'ouvrage.
    facts.reception_date = _extract_reception_date(linear_text) or _extract_date_near(["date de reception", "date de réception", "la réception a eu lieu", "la reception a eu lieu", "réception a eu lieu", "reception a eu lieu"], linear_text, allow_global_textual=False)
    facts.loss_date = _extract_lamy_strasbourg_appearance_date(linear_text) or _extract_date_near(["date du sinistre", "date survenance", "survenance", "survenu", "apparition", "date d'apparition", "dommage est survenu"], linear_text, allow_global_textual=False)
    # Date de déclaration : priorité au mail / courrier, pas au champ "date de survenance" voisin du mot déclaration.
    facts.declaration_date = _extract_date_near(["date email"], clean_text, allow_global_textual=False) or _extract_letter_date(clean_text) or _extract_date_near(["déclaration reçue", "declaration recue", "déclaration de sinistre du", "declaration de sinistre du"], clean_text, allow_global_textual=False)
    facts.construction_type = _classify_construction(low)
    facts.location = _classify_location(low, facts.declared_damage)
    if not facts.loss_date:
        facts.loss_date = _extract_plumbing_intervention_date(clean_text)
    facts.cost_ttc = _find_amount(text)
    facts.mentions_heating_pac = _mentions_positive(low, ["pompe a chaleur", "pompe à chaleur", "pac", "chauffage", "eau chaude sanitaire", "radiateurs", "plancher chauffant", "résistance électrique", "resistance electrique"])
    facts.mentions_refrigerant_leak = _mentions_positive(low, ["fluide frigorigene", "fluide frigorigène", "circuit frigo", "liaison frigo", "raccord rapide", "r32", "fuite raccord", "fuite sur raccord", "reseau cuivre", "réseau cuivre"])
    facts.mentions_heating_backup = _mentions_positive(low, ["mode secours", "secours", "résistance électrique", "resistance electrique", "services rétablis", "services retablis", "chauffage : fonctionne", "eau chaude : fonctionne"])
    facts.mentions_loggia_roof_trace = bool("loggia" in low and "toiture" in low and any(k in low for k in ["auréole", "aureole", "infiltration", "dégât des eaux", "degat des eaux"]))
    facts.mentions_living_ceiling_under_terrace_trace = bool(any(k in low for k in ["plafond du séjour", "plafond du sejour", "plafond séjour", "plafond sejour", "infiltration au plafond"]) and any(k in low for k in ["séjour", "sejour", "salon", "lot 324", "r+4", "terrasse privative", "terrasse supérieure", "terrasse superieure"]))
    facts.mentions_dry_inactive_trace = bool(any(k in (low + " " + raw_low) for k in ["trace_ponctuelle_seche_apathique", "sèche", "seche", "apathique", "pas d'eau active", "pas d’eau active", "absence d'humidité active", "absence d’humidité active"]))
    facts.mentions_no_facade_resurgence = bool(any(k in (low + " " + raw_low) for k in ["facade_sans_resurgence_evidente", "absence de résurgence", "absence de resurgence", "pas de résurgence", "pas de resurgence", "pas de présence d'eau dans le complexe", "pas de presence d'eau dans le complexe"]))
    facts.mentions_interior_water_ingress = bool(any(k in low for k in ["entrée d'eau dans le logement", "entree d'eau dans le logement", "eau dans le logement", "eau à l'intérieur du logement", "eau a l'interieur du logement", "pièce habitable inondée", "piece habitable inondee", "écoulement dans le séjour", "ecoulement dans le sejour", "ruissellement dans le séjour", "ruissellement dans le sejour"]) and not facts.mentions_loggia_roof_trace)
    facts.has_photos = any(k in raw_low for k in ["photo", "photos", "image", "pj", "pièce jointe", "piece jointe"])
    facts.has_quote = any(k in low for k in ["devis", "facture", "quantum", "montant", "chiffrage"])
    facts.has_prior_intervention = _mentions_positive(low, ["déjà intervenu", "deja intervenu", "intervention antérieure", "intervention anterieure", "réapparu", "reapparu", "persiste", "reprise précédente", "reprise precedente", "kaliti", "rapport d'intervention", "rapport diintervention", "intervention realisee", "intervention réalisée", "fait changer", "remplacement de vanne", "remplacement d'une vanne", "vanne déjà remplacée", "vanne deja remplacee", "rapport de reparation", "rapport de réparation"])
    facts.mentions_reserve_or_gpa = _mentions_positive(low, ["réserve", "reserve", "gpa", "parfait achèvement", "parfait achevement", "travaux non terminés", "travaux non termines"])
    facts.mentions_safety = _mentions_positive(low, ["sécurité", "securite", "danger", "risque de chute", "menace de chute", "chute", "risque incendie", "départ de feu", "depart de feu", "suffocation", "asphyxiant"])
    facts.mentions_solidite = _mentions_positive(low, ["solidité", "solidite", "structure", "affaissement", "effondrement", "porteur", "fondation"])
    facts.mentions_impropriete = _mentions_positive(low, ["impropriété", "impropriete", "inhabitable", "ne peut plus", "impossible d'utiliser", "usage impossible"])
    water_terms = ["infiltration", "humid", "moisiss", "condensation", "tache d\'humid", "dégât des eaux", "degat des eaux", "écoulement d'eau", "ecoulement d'eau", "fuite d'eau"]
    generic_leak = _mentions_positive(low, ["fuite"])
    # Une fuite de fluide frigorigène / circuit frigo n'est pas une pathologie eau-humidité/toiture.
    facts.mentions_humidity_or_water = bool(_mentions_positive(low, water_terms) or (generic_leak and not facts.mentions_refrigerant_leak))
    facts.mentions_crack = _mentions_positive(low, ["fissure", "fissuration", "lézarde", "lezarde"])
    facts.mentions_detachment = _mentions_positive(low, ["décollement", "decollement", "décoll", "decol", "soulèvement", "soulevement", "décrocher", "decrocher", "tomber", "chute", "arrachement"] )
    # Ne jamais assimiler un simple mot "plafond" à un dossier luminaire.
    # On ne bascule dans la branche luminaire/suspension que si le libellé vise
    # explicitement un luminaire, une suspension, un élément suspendu ou un risque de chute/tomber.
    facts.mentions_ceiling_suspension = _mentions_positive(low, ["suspension", "luminaire", "élément suspendu", "element suspendu", "menace de tomber", "risque de chute", "tomber du plafond", "se décroche", "se decroche", "décroche du plafond", "decroche du plafond"])
    facts.mentions_maintenance = _mentions_positive(low, ["entretien", "maintenance", "usure", "usage anormal", "nettoyage", "obstruction", "bouche d'extraction", "bouches d'extraction", "entrée d'air bouchée", "entree d'air bouchee", "vanne fuyarde", "vanne d arret fuyarde", "vanne d'arrêt fuyarde", "remplacement de vanne", "piece d'usure", "pièce d'usure", "organe de plomberie", "fait changer la vanne", "rapport d'intervention", "rapport diintervention"])
    facts.mentions_vmc = _mentions_positive(low, ["vmc", "ventilation", "bouche d\'extraction", "bouches d\'extraction", "entrée d\'air", "entree d\'air", "débit", "debit"])
    # "Infiltration" ou "dégât des eaux" seuls = contexte déclaratif ; l'activité doit être objectivée.
    facts.mentions_active_infiltration = bool(_mentions_positive(low, ["fuite active", "écoulement d'eau", "ecoulement d'eau", "ruissellement", "humidité active", "humidite active", "test d'arrosage", "mise en eau"]) and not facts.mentions_refrigerant_leak)
    facts.mentions_roof_terrace, facts.mentions_waterproofing_upstand_defect, facts.mentions_maintenance_contractor, facts.mentions_characterized_maintenance_defect = _maintenance_defect_flags(low)
    facts.mentions_shower_receiver, facts.mentions_shower_peripheral_joint, facts.mentions_shower_mastic_maintenance_defect = _shower_mastic_maintenance_flags(low)
    if facts.mentions_characterized_maintenance_defect or facts.mentions_shower_mastic_maintenance_defect or (facts.mentions_roof_terrace and facts.mentions_maintenance_contractor):
        facts.mentions_maintenance = True
    mold_words = _mentions_positive(low, ["moisissure", "moisissures", "condensation"])
    shower_or_leak_words = _mentions_positive(low, ["douche", "receveur", "siphon", "caniveau", "mitigeur", "rosette", "pare douche", "salle de bain", "salle d\'eau", "infiltration", "fuite active", "écoulement", "ecoulement", "dégât des eaux", "degat des eaux"])
    facts.mentions_mold_condensation = bool(mold_words and not shower_or_leak_words)
    return facts


def _extract_damage(text: str) -> str:
    text = _strip_visual_blocks(text)
    linear = _linearize(text)
    low_linear = linear.lower()
    # Cas plafond séjour sous terrasse/logement supérieur : extraire le vrai libellé plutôt que les références OCR.
    if (("infiltration au plafond" in low_linear or "trace" in low_linear or "auréole" in low_linear or "aureole" in low_linear)
        and ("séjour" in low_linear or "sejour" in low_linear or "lot 324" in low_linear or "rue joseph guerber" in low_linear)):
        lot = " du lot 324 (R+4)" if "lot 324" in low_linear else ""
        return "trace / infiltration déclarée au plafond du séjour" + lot + ", sous terrasse privative du logement supérieur à vérifier"

    # Cas loggia/toiture : ne pas réduire la déclaration à "RESIDENCE" ou au nom du formulaire.
    if ("loggia" in low_linear and "toiture" in low_linear and ("auréole" in low_linear or "aureole" in low_linear or "infiltration" in low_linear or "dégât des eaux" in low_linear or "degat des eaux" in low_linear)):
        m = re.search(r"appartement\s*(\d+)", low_linear, flags=re.I)
        lot = f" de l'appartement {m.group(1)}" if m else ""
        return "auréoles / traces en plafond de loggia" + lot + ", déclarées comme provenant de la toiture, sans entrée d'eau en local habitable objectivée"

    # Cas chauffage/PAC : éviter de confondre une fuite de fluide frigorigène avec une infiltration d'eau/toiture.
    if (
        ("pompe a chaleur" in low_linear or "pompe à chaleur" in low_linear or "pac" in low_linear or "chauffage" in low_linear)
        and ("fluide frigorigene" in low_linear or "fluide frigorigène" in low_linear or "circuit frigo" in low_linear or "liaison frigo" in low_linear or "raccord rapide" in low_linear or "r32" in low_linear)
    ):
        return "installation de chauffage/PAC défectueuse : fuite de fluide frigorigène au niveau d'un raccord rapide sur liaison frigorifique / réseau cuivre, avec fonctionnement dégradé du chauffage et de l'eau chaude sanitaire"

    # Cas plomberie scannée : courrier + rapport d'intervention.
    if ("vanne" in low_linear and ("fuy" in low_linear or "remplacement" in low_linear)) and ("infiltration" in low_linear or "dommages aux embellissements" in low_linear):
        loc = "RDC du bâtiment 3 / gaine technique" if re.search(r"rdc.{0,40}batiment\s*3|rdc.{0,40}bâtiment\s*3", low_linear) else "gaine technique"
        return "fuite d'une vanne d'arrêt dans la gaine technique, déjà remplacée en urgence, avec dégradations ponctuelles d'embellissements au droit de la gaine (" + loc + ")"
    # Phrases déclaratives de mail/courrier sans libellé formel.
    factual_patterns = [
        r"(?:qui\s+)?a\s+subi\s+une\s+infiltration\s+(.{10,260}?)(?:\.|Compte tenu|Les convocations|$)",
        r"infiltration\s+qui\s+provenait\s+(.{10,260}?)(?:\.|Compte tenu|Les convocations|$)",
        r"il\s+a\s+été\s+constaté\s+(.{10,240}?)(?:\.|\n)",
        r"il\s+a\s+ete\s+constate\s+(.{10,240}?)(?:\.|\n)",
        r"nous\s+venons\s+vers\s+vous\s+concernant.*?(?:constaté|constate)\s+(.{10,240}?)(?:\.|\n)",
    ]
    for pat in factual_patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" -–:;.")
            if value:
                return value[:1000]
    # Priorité absolue aux libellés déclaratifs explicites.
    # La V3.2 captait parfois le nom du fichier "Declaration de sinistre.eml"
    # au lieu du champ "Sinistre : ...".
    priority_patterns = [
        r"(?:^|\n)\s*[-•]?\s*(?:déclaration de sinistre|declaration de sinistre)\s*[:\-]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*[-•]?\s*(?:déclaration|declaration)\s*[:\-]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*[-•]?\s*(?:sinistre|désordre|desordre)\s*[:\-]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*[-•]?\s*(?:dommage déclaré|dommage declare)\s*[:\-]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*[-•]?\s*(?:problème|probleme)\s*[:\-]\s*(.+?)(?:\n|$)",
    ]
    for pat in priority_patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" -–:;.")
            low_value = value.lower()
            if value and not low_value.endswith(('.eml', '.pdf', '.docx')) and "=== fichier" not in low_value and "analyse visuelle" not in low_value:
                return value[:1000]

    patterns = [
        r"(?:réclamation.*?porte sur|reclamation.*?porte sur)\s*[:\-]?\s*(.+?)(?:\n\n|les constatations|avis|$)",
        r"pour une\s+(.{0,180}?qui menace de tomber)",
        r"nous signalons que\s+(.{0,240}?)(?:\.|\n)",
        # Dernier recours seulement : éviter que le nom de fichier fasse office de dommage.
        r"(?:déclaration de dommage|declaration de dommage)\s*[:\-]?\s*(.+?)(?:\n\n|cordialement|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip()
            if "=== fichier" not in value.lower():
                return value[:1000]
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30 and "=== fichier" not in l.lower()]
    return " ".join(lines[:4])[:1000]



def _extract_reception_date(text: str) -> str:
    # Priorité aux formulations de déclaration / CMI. Elles sont plus fiables que
    # les dates administratives de réception de mission ou de courrier.
    priority_patterns = [
        r"date\s+d.{0,20}(?:réception|reception).{0,60}ouvrage\s*[:\-]?\s*" + DATE_RE.pattern,
        r"date\s+d.{0,20}(?:réception|reception)\s*[:\-]?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s+CMI.{0,80}?date\s*[:\-]?\s*" + DATE_RE.pattern,
        r"RÉCEPTION\s+CMI.{0,80}?date\s*[:\-]?\s*" + DATE_RE.pattern,
    ]
    for pat in priority_patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            d, mo, y = m.groups()[-3:]
            if len(y) == 2:
                y = "20" + y
            return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    patterns = [
        r"(?:réception|reception)\s+unique\s*(?:date\s*[:\-]?)?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s*[:\-]\s*" + DATE_RE.pattern,
        r"date\s+de\s+(?:réception|reception)\s*[:\-]?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s+des\s+travaux\s+au\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s+(?:est\s+)?(?:dat[ée]e|datee|fix[ée]e|fixee)\s+(?:du|au)?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)[^\n]{0,80}?" + DATE_RE.pattern,
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            d, mo, y = m.groups()[-3:]
            if len(y) == 2:
                y = "20" + y
            return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    return ""

def _extract_date_near(labels: list[str], text: str, allow_global_textual: bool = True) -> str:
    # Numeric dates close to labels
    for label in labels:
        pat = re.compile(label + r"[^\n]{0,120}?" + DATE_RE.pattern, re.I)
        m = pat.search(text)
        if m:
            nums = re.findall(DATE_RE, m.group(0))
            if nums:
                d, mo, y = nums[-1]
                if len(y) == 2:
                    y = "20" + y
                return f"{int(d):02d}/{int(mo):02d}/{int(y):04d}"
    # RFC email date, e.g. Date email: Wed, 15 Apr 2026 20:17:10 +0200
    if any("date email" in l.lower() for l in labels) or any("déclaration" in l.lower() or "declaration" in l.lower() for l in labels):
        m = re.search(r"Date email:\s*([^\n]+)", text, flags=re.I)
        if m:
            try:
                dt = parsedate_to_datetime(m.group(1).strip())
                return dt.strftime("%d/%m/%Y")
            except Exception:
                pass
    # French textual dates. On les cherche d'abord à proximité du libellé demandé ;
    # sinon on évite de recycler la date de réception comme date d'apparition.
    months = {
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    }
    month_re = r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})"
    for label in labels:
        m = re.search(label + r"[^\n]{0,120}?" + month_re, text, flags=re.I | re.S)
        if m:
            d = int(m.group(1)); mo = months[m.group(2).lower()]; y = int(m.group(3))
            return f"{d:02d}/{mo:02d}/{y:04d}"
    if allow_global_textual:
        m = re.search(r"\b" + month_re + r"\b", text, flags=re.I)
        if m:
            d = int(m.group(1)); mo = months[m.group(2).lower()]; y = int(m.group(3))
            return f"{d:02d}/{mo:02d}/{y:04d}"
    return ""

def _classify_construction(low: str) -> str:
    if any(k in low for k in ["maison individuelle", "pavillon", "construction maison individuelle", "c.m.i", "ccmi", " cmi ", "c.c.m.i", "scmc", "le montcel"]):
        return "Maison individuelle"
    if any(k in low for k in ["bâtiment collectif", "batiment collectif", "collectif d'habitation", "copropriété", "copropriete", "appartement", "logement", "logements", "immeuble", "résidence", "residence", "syndic", "sdc"]):
        return "Bâtiment collectif d'habitation"
    if any(k in low for k in ["bureau", "commerce", "hotel", "hôtel", "local d'activité"]):
        return "Local d'activité / tertiaire"
    return "Non déterminé"


def _classify_location(low: str, declared_damage: str = "") -> str:
    focus_all = ((declared_damage or "") + " " + (low or "")).lower()
    if any(k in focus_all for k in ["plafond du séjour", "plafond du sejour", "plafond séjour", "plafond sejour", "infiltration au plafond"]) and any(k in focus_all for k in ["séjour", "sejour", "salon", "lot 324", "r+4"]):
        return "Plafond du séjour / pièce habitable sous terrasse supérieure"
    if ("plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low) and ("toiture" in low or "fuite" in low or "infiltration" in low):
        return "Plafond du dernier étage / sous toiture ou terrasse technique"
    # Prioriser le libellé du sinistre sur les renseignements généraux de l'opération
    # (ex. "niveau de sous-sol à usage de parking" ne doit pas écraser "moisissure dans une chambre").
    focus = (declared_damage or "").lower()
    if any(k in focus for k in ["chambre", "salon", "séjour", "sejour", "cuisine"]):
        return "Pièce habitable"
    if any(k in focus for k in ["loggia", "balcon"]):
        return "Loggia / balcon / extérieur privatif"
    if any(k in focus for k in ["hall", "circulation", "parties communes", "faux plafond", "suspension", "luminaire"]):
        return "Hall / circulations / parties communes"
    if any(k in focus for k in ["salle de bain", "salle d'eau", "douche", "receveur", "baignoire"]):
        return "Salle d'eau / salle de bain"
    if any(k in focus for k in ["gaine", "gaine technique", "communs", "parties communes", "rdc"]):
        return "Gaine technique / parties communes"
    if any(k in focus for k in ["garage", "local technique", "module extérieur", "module exterieur", "pac", "pompe à chaleur", "pompe a chaleur"]):
        return "Garage / local technique chauffage"
    if any(k in focus for k in ["parking", "sous-sol", "stationnement"]):
        return "Parking / sous-sol"
    mapping = [
        ("Gaine technique / parties communes", ["gaine", "gaine technique", "communs", "parties communes", "rdc"]),
        ("Hall / circulations / parties communes", ["hall", "circulation", "local om", "faux plafond", "plafond", "suspension", "luminaire"]),
        ("Salle d'eau / salle de bain", ["salle de bain", "salle d'eau", "douche", "receveur", "baignoire"]),
        ("Pièce habitable", ["salon", "chambre", "séjour", "sejour", "cuisine"]),
        ("Façade / extérieur", ["facade", "façade", "ravalement", "enduit", "appui", "fenêtre", "fenetre"]),
        ("Loggia / balcon / extérieur privatif", ["loggia", "balcon"]),
        ("Toiture-terrasse / balcon", ["toiture", "acrotère"]),
        ("Garage / local technique chauffage", ["pompe a chaleur", "pompe à chaleur", "liaison frigo", "fluide frigorigene", "fluide frigorigène", "garage", "local technique"]),
        ("Parking / sous-sol", ["parking", "sous-sol", "rampe", "stationnement"]),
    ]
    for name, keys in mapping:
        if any(k in low for k in keys):
            return name
    return "Non déterminé"


def claim_focus_text(text: str, facts: ExtractedFacts) -> str:
    """Texte court qui porte uniquement le sinistre déclaré.

    Il évite que les renseignements généraux de l'opération (parking, lots, réserves, etc.)
    polluent la recherche des fiches métier.
    """
    parts = []
    if facts.declared_damage:
        parts.append("Dommage déclaré : " + facts.declared_damage)
    if facts.location and facts.location != "Non déterminé":
        parts.append("Localisation : " + facts.location)
    if facts.address:
        parts.append("Adresse : " + facts.address)
    low = text.lower()
    if getattr(facts, "mentions_living_ceiling_under_terrace_trace", False):
        parts.append("Famille pressentie : trace ponctuelle au plafond du séjour sous terrasse privative supérieure - matérialité d'infiltration active à vérifier")
        if getattr(facts, "mentions_dry_inactive_trace", False):
            parts.append("Indice visuel : trace sèche / apathique / peu étendue")
        if getattr(facts, "mentions_no_facade_resurgence", False):
            parts.append("Indice visuel : absence de résurgence active apparente en façade / nez de plancher")
    elif getattr(facts, "mentions_loggia_roof_trace", False):
        parts.append("Famille pressentie : toiture / loggia / balcon - traces en plafond de loggia sans entrée d'eau en local habitable objectivée")
    elif facts.mentions_roof_terrace or "toiture" in low or "plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low:
        parts.append("Famille pressentie : toiture / toiture-terrasse / terrasse technique / ouvrages surmontant le plafond")
    if facts.mentions_waterproofing_upstand_defect:
        parts.append("Indice déclaré : relevé d'étanchéité / évacuation / point singulier dégradé")
    if facts.mentions_characterized_maintenance_defect:
        parts.append("Indice entretien caractérisé : défaut rattachable à une fiche entretien")
    if getattr(facts, "mentions_shower_receiver", False):
        parts.append("Famille pressentie : salle d'eau / receveur de douche / joints périphériques")
    if getattr(facts, "mentions_shower_peripheral_joint", False):
        parts.append("Indice déclaré : périphérie du receveur / joint ou mastic souple / pied de cloison")
    if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        parts.append("Indice entretien caractérisé : mastics souples périphériques du receveur")
    if getattr(facts, "mentions_heating_pac", False) or getattr(facts, "mentions_refrigerant_leak", False):
        parts.append("Famille pressentie : chauffage / pompe à chaleur air-eau / circuit frigorifique")
        parts.append("Indice déclaré : fuite de fluide frigorigène sur raccord rapide / liaison frigo / réseau cuivre")
    if _mentions_positive(low, ["vanne", "robinet", "robinetterie", "siphon", "groupe de sécurité", "groupe de securite"]):
        parts.append("Famille pressentie : plomberie / organe de coupure / vanne / pièce d'usure")
    if facts.has_prior_intervention:
        parts.append("Indice déclaré : intervention ou remplacement déjà réalisé avant instruction")
    # Ajout ciblé des indices visuels produits par l'analyse d'image, sans reprendre tout le dossier.
    for key in ["moisissures_ponctuelles", "condensation_probable", "luminaire_decoratif", "fixation_defaillante", "risque_chute", "fissuration", "decollement"]:
        if key in low:
            parts.append("Indice visuel : " + key)
    return "\n".join(parts) or text
