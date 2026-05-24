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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _find_amount(text: str) -> Optional[float]:
    """Extrait un coût travaux/réparation, en privilégiant les montants TTC proches du quantum.

    La V2 prenait le plus petit montant en euros, ce qui captait parfois des montants parasites
    (capital, coût de construction, références, honoraires). La V3 score les contextes.
    """
    amount_pat = re.compile(r"(\d{1,3}(?:[ .]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|EUR|euros?)", re.I)
    candidates = []
    for m in amount_pat.finditer(text):
        raw = m.group(1)
        try:
            value = float(raw.replace(" ", "").replace(".", "").replace(",", "."))
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
        if any(k in ctx for k in ["quantum", "réparation", "reparation", "travaux", "coût", "cout", "chiffrage", "estime", "montant"]):
            score += 25
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
    low = clean_text.lower()
    raw_low = (text or "").lower()
    facts = ExtractedFacts()
    facts.declared_damage = _extract_damage(clean_text)
    facts.operation = _extract_line_after(r"(?:opération|operation|résidence|residence|affaire)", clean_text)
    facts.address = _extract_line_after(r"(?:adresse du risque|adresse|site)", clean_text) or _extract_address_from_subject_or_text(clean_text)
    facts.claimant = _extract_claimant_from_text(clean_text) or _extract_line_after(r"(?:coordonnées du propriétaire|assuré|beneficiaire|bénéficiaire|demandeur|propriétaire)", clean_text)
    facts.reception_date = _extract_reception_date(clean_text) or _extract_date_near(["date de reception", "date de réception", "réception", "reception"], clean_text)
    facts.loss_date = _extract_date_near(["date du sinistre", "survenu", "apparition", "dommage est survenu"], clean_text, allow_global_textual=False)
    facts.declaration_date = _extract_date_near(["date email", "déclaration", "declaration", "déclaré", "declare"], clean_text)
    facts.construction_type = _classify_construction(low)
    facts.location = _classify_location(low, facts.declared_damage)
    facts.cost_ttc = _find_amount(text)
    facts.has_photos = any(k in raw_low for k in ["photo", "photos", "image", "pj", "pièce jointe", "piece jointe"])
    facts.has_quote = any(k in low for k in ["devis", "facture", "quantum", "montant", "chiffrage"])
    facts.has_prior_intervention = _mentions_positive(low, ["déjà intervenu", "deja intervenu", "intervention antérieure", "intervention anterieure", "réapparu", "reapparu", "persiste", "reprise précédente", "reprise precedente", "kaliti"])
    facts.mentions_reserve_or_gpa = _mentions_positive(low, ["réserve", "reserve", "gpa", "parfait achèvement", "parfait achevement", "travaux non terminés", "travaux non termines"])
    facts.mentions_safety = _mentions_positive(low, ["sécurité", "securite", "danger", "chute", "incendie", "risque"])
    facts.mentions_solidite = _mentions_positive(low, ["solidité", "solidite", "structure", "affaissement", "effondrement", "porteur", "fondation"])
    facts.mentions_impropriete = _mentions_positive(low, ["impropriété", "impropriete", "inhabitable", "ne peut plus", "impossible d'utiliser", "usage impossible"])
    facts.mentions_humidity_or_water = _mentions_positive(low, ["infiltration", "humid", "moisiss", "fuite", "condensation", "tache d\'humid", "dégât des eaux", "degat des eaux"])
    facts.mentions_crack = _mentions_positive(low, ["fissure", "fissuration", "lézarde", "lezarde"])
    facts.mentions_detachment = _mentions_positive(low, ["décollement", "decollement", "décoll", "decol", "soulèvement", "soulevement", "décrocher", "decrocher", "tomber", "chute", "arrachement"] )
    # Ne jamais assimiler un simple mot "plafond" à un dossier luminaire.
    # On ne bascule dans la branche luminaire/suspension que si le libellé vise
    # explicitement un luminaire, une suspension, un élément suspendu ou un risque de chute/tomber.
    facts.mentions_ceiling_suspension = _mentions_positive(low, ["suspension", "luminaire", "élément suspendu", "element suspendu", "menace de tomber", "risque de chute", "tomber du plafond", "se décroche", "se decroche", "décroche du plafond", "decroche du plafond"])
    facts.mentions_maintenance = _mentions_positive(low, ["entretien", "maintenance", "usure", "usage anormal", "nettoyage", "obstruction", "bouche d\'extraction", "bouches d\'extraction", "entrée d\'air bouchée", "entree d\'air bouchee"])
    facts.mentions_vmc = _mentions_positive(low, ["vmc", "ventilation", "bouche d\'extraction", "bouches d\'extraction", "entrée d\'air", "entree d\'air", "débit", "debit"])
    facts.mentions_active_infiltration = _mentions_positive(low, ["infiltration", "fuite active", "écoulement", "ecoulement", "dégât des eaux", "degat des eaux", "test d\'arrosage", "mise en eau"])
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
    # Phrases déclaratives de mail/courrier sans libellé formel.
    factual_patterns = [
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
    patterns = [
        r"(?:réception|reception)\s+unique\s*(?:date\s*[:\-]?)?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s*[:\-]\s*" + DATE_RE.pattern,
        r"date\s+de\s+(?:réception|reception)\s*[:\-]?\s*" + DATE_RE.pattern,
        r"(?:réception|reception)\s+des\s+travaux\s+au\s*" + DATE_RE.pattern,
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
    if any(k in low for k in ["bâtiment collectif", "batiment collectif", "collectif d'habitation", "copropriété", "copropriete", "appartement", "logement", "logements"]):
        return "Bâtiment collectif d'habitation"
    if any(k in low for k in ["maison individuelle", "pavillon"]):
        return "Maison individuelle"
    if any(k in low for k in ["bureau", "commerce", "hotel", "hôtel", "local d'activité"]):
        return "Local d'activité / tertiaire"
    return "Non déterminé"


def _classify_location(low: str, declared_damage: str = "") -> str:
    if ("plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low) and ("toiture" in low or "fuite" in low or "infiltration" in low):
        return "Plafond du dernier étage / sous toiture ou terrasse technique"
    # Prioriser le libellé du sinistre sur les renseignements généraux de l'opération
    # (ex. "niveau de sous-sol à usage de parking" ne doit pas écraser "moisissure dans une chambre").
    focus = (declared_damage or "").lower()
    if any(k in focus for k in ["chambre", "salon", "séjour", "sejour", "cuisine"]):
        return "Pièce habitable"
    if any(k in focus for k in ["hall", "circulation", "parties communes", "faux plafond", "plafond", "suspension", "luminaire"]):
        return "Hall / circulations / parties communes"
    if any(k in focus for k in ["salle de bain", "salle d'eau", "douche", "receveur", "baignoire"]):
        return "Salle d'eau / salle de bain"
    if any(k in focus for k in ["parking", "sous-sol", "garage", "stationnement"]):
        return "Parking / sous-sol"
    mapping = [
        ("Hall / circulations / parties communes", ["hall", "circulation", "local om", "parties communes", "faux plafond", "plafond", "suspension", "luminaire"]),
        ("Salle d'eau / salle de bain", ["salle de bain", "salle d'eau", "douche", "receveur", "baignoire"]),
        ("Pièce habitable", ["salon", "chambre", "séjour", "sejour", "cuisine"]),
        ("Façade / extérieur", ["facade", "façade", "ravalement", "enduit", "appui", "fenêtre", "fenetre"]),
        ("Toiture-terrasse / balcon", ["toiture", "balcon", "loggia", "acrotère"]),
        ("Parking / sous-sol", ["parking", "sous-sol", "rampe", "garage", "stationnement"]),
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
    if facts.mentions_roof_terrace or "toiture" in low or "plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low:
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
    # Ajout ciblé des indices visuels produits par l'analyse d'image, sans reprendre tout le dossier.
    for key in ["moisissures_ponctuelles", "condensation_probable", "luminaire_decoratif", "fixation_defaillante", "risque_chute", "fissuration", "decollement"]:
        if key in low:
            parts.append("Indice visuel : " + key)
    return "\n".join(parts) or text
