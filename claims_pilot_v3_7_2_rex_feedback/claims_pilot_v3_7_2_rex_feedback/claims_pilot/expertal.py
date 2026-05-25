from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .extractor import ExtractedFacts
from .retrieval import RetrievedSource
from .decision import DecisionResult, years_since_reception
from .evidence import EvidenceAssessment
from .visual import ImageFinding
from .methodology import assess_methodology


@dataclass
class ExpertalAnalysis:
    declared_damage: str
    analysed_damage: str
    chronology: str
    decade_year: str
    construction_context: str
    location_context: str
    visual_context: str
    affected_element_category: str
    affected_element_detail: str
    pathology_signs: List[str]
    likely_causes: List[str]
    severity_assessment: str
    impropriete_markers: List[str]
    cause_etrangere_screening: str
    guarantee_analysis: str
    repair_principle: str
    pricing_comment: str
    elements_to_obtain: List[str]
    reasoning_path: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _year_label(years: Optional[float]) -> tuple[str, str]:
    if years is None:
        return "Non déterminée", "Date de réception et/ou date de sinistre/déclaration manquante."
    if years < 0 or years > 10:
        return "Hors période décennale apparente", f"Le sinistre apparaît à {years:.1f} ans de la réception."
    rank = int(years) + 1
    if rank <= 1:
        note = "1ère année : attention GPA / mise en demeure / réserves et absence de traitement TM automatique."
    elif rank <= 2:
        note = "Début de décennale : lorsqu'un désordre technique apparaît très tôt, la piste du défaut constructif est renforcée, sauf indice contraire."
    elif rank <= 7:
        note = "Milieu de décennale : analyse équilibrée entre défaut constructif, évolution normale, usage et entretien selon la famille d'ouvrage."
    else:
        note = "Fin de décennale : l'entretien, l'usure ou l'usage ne peuvent être envisagés que si une fiche et un indice concret les rendent pertinents."
    return f"Année {rank} de la décennale", note


def _is_top(retrieved: List[RetrievedSource], ids: set[str], limit: int = 4) -> bool:
    return any(r.card.id in ids for r in retrieved[:limit])


def _maintenance_kind(facts: ExtractedFacts, retrieved: List[RetrievedSource], raw_text: str = "") -> str:
    method = assess_methodology(facts, retrieved, raw_text)
    return method.entretien_kind if method.defaut_entretien_caracterise else ""


def _is_characterized_maintenance_defect(facts: ExtractedFacts, retrieved: List[RetrievedSource]) -> bool:
    return bool(_maintenance_kind(facts, retrieved))

def _is_top_floor_roof_leak(facts: ExtractedFacts, raw_text: str) -> bool:
    low = (raw_text or "").lower()
    damage = (getattr(facts, "declared_damage", "") or "").lower()
    return bool(("fuite" in low or "infiltration" in low or "humid" in low)
        and ("plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low or "plafond du dernier" in damage)
        and ("toiture" in low or "terrasse technique" in low or "édicule" in low or "edicule" in low or "dernier étage" in low or "dernier etage" in low))


def _affected_element(facts: ExtractedFacts, retrieved: List[RetrievedSource]) -> tuple[str, str]:
    ids = [r.card.id for r in retrieved[:4]]
    kind = _maintenance_kind(facts, retrieved)
    if kind == "douche_mastic":
        return "Équipement sanitaire / joint périphérique soumis à entretien", "Receveur de douche et mastics souples périphériques : le maintien en bon état d'usage des joints relève de l'entretien courant."
    if kind == "roof_upstand":
        return "Étanchéité / point singulier soumis à entretien", "Relevé d'étanchéité ou point singulier de toiture-terrasse dont le bon état doit être surveillé et entretenu."
    yrs = years_since_reception(facts)
    if getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and yrs is not None and yrs < 2.0:
        return "Équipement sanitaire / étanchéité périphérique à instruire", "Receveur de douche, calage/stabilité, joints périphériques et joint du plombier : origine constructive à rechercher avant toute hypothèse d'entretien."
    if facts.mentions_mold_condensation or any(i in ids for i in ["VMC_CONDENSATION"]):
        return "Parement intérieur / ventilation", "Traces superficielles sur revêtement intérieur ; ventilation/VMC à contrôler si le faciès évoque une condensation."
    if any(i in ids for i in ["FACADE_INFILTRATION", "ETANCHEITE_TOITURE_TERRASSE_BALCON"]):
        return "Élément constitutif du clos / couvert", "Étanchéité, façade, menuiserie extérieure, joint ou dispositif participant au clos et couvert."
    if any(i in ids for i in ["GROS_OEUVRE_STRUCTURE"]):
        return "Élément constitutif de l'ossature", "Fondations, murs porteurs, poteaux, poutres, planchers, dalles, charpente ou voiles."
    if any(i in ids for i in ["PLOMBERIE_RESEAUX"]):
        return "Élément de viabilité / réseau", "Réseau d'alimentation ou d'évacuation, canalisation, collecteur ou ouvrage de gestion des eaux."
    if any(i in ids for i in ["VMC_CONDENSATION"]):
        return "Élément d'équipement fonctionnel", "Installation destinée à fonctionner : ventilation, extraction, chauffage, climatisation ou autre équipement technique."
    if any(i in ids for i in ["SUSPENSION_FAUX_PLAFOND_SECURITE"]):
        return "Élément d'équipement dissociable destiné à fonctionner", "Luminaire décoratif électrique / suspension décorative fixée au faux plafond. L'élément affecté est le luminaire et sa fixation, non le faux plafond dans son ensemble."
    if any(i in ids for i in ["CARRELAGE_SOL", "FAIENCE_MURALE_SECURITE", "DOUCHE_ZERO_RESSAUT"]):
        return "Élément d'équipement inerte", "Revêtement de sol ou mural, faïence, cloison, équipement sanitaire ou finition incorporée."
    if facts.mentions_ceiling_suspension:
        return "Élément d'équipement dissociable destiné à fonctionner", "Luminaire décoratif électrique / suspension décorative fixée au faux plafond. L'élément affecté est le luminaire et sa fixation, non le faux plafond dans son ensemble."
    if facts.mentions_humidity_or_water:
        return "Élément à préciser", "Le dossier évoque un phénomène d'eau ; il faut identifier si l'élément affecté relève du clos/couvert, d'un réseau ou d'un local humide."
    return "Non déterminé", "L'élément affecté n'est pas suffisamment identifié dans les pièces reçues."


def _zone_context(facts: ExtractedFacts) -> str:
    loc = facts.location or "Non déterminé"
    if "Salle" in loc:
        return f"{loc} : pièce d'eau / local humide ; les pathologies d'étanchéité, de réseaux, de joints, de SPEC/SEL ou de revêtements sont à privilégier."
    if "Hall" in loc:
        return f"{loc} : partie commune accessible ; le risque pour les personnes pèse fortement dans l'analyse de l'impropriété."
    if "Parking" in loc:
        return f"{loc} : zone non habitable / sous-sol ; on raisonne surtout sécurité, accessibilité, infiltrations ou atteinte à l'usage des ouvrages communs."
    if "Façade" in loc or "Toiture" in loc:
        return f"{loc} : zone extérieure ou exposée ; analyse orientée clos/couvert, étanchéité, ruissellement et points singuliers."
    if "Pièce habitable" in loc:
        if getattr(facts, "mentions_mold_condensation", False):
            return f"{loc} : chambre ou local habitable ; les moisissures ponctuelles doivent être distinguées d'une infiltration active ou d'une impropriété réelle."
        return f"{loc} : partie habitable noble ; l'humidité, l'impossibilité d'usage ou le risque sécurité peuvent rapidement caractériser une impropriété."
    return "Localisation non déterminée : demander une photo large ou un plan de situation pour savoir si l'on est en partie habitable, pièce d'eau, partie commune, parking, façade ou extérieur."


def _visual_context(findings: Optional[List[ImageFinding]], facts: ExtractedFacts) -> str:
    findings = findings or []
    exploitable = [f for f in findings if f.status in {"EXPLOITABLE", "PARTIEL"}]
    if not findings:
        if facts.has_photos:
            return "Des photos sont annoncées, mais l'analyse visuelle n'a pas pu les qualifier automatiquement."
        return "Aucune photo exploitable n'est reçue : la matérialité repose seulement sur le déclaratif."
    if not exploitable:
        return "Des images sont reçues mais elles sont peu exploitables : demander des vues plus nettes, une vue d'ensemble et une vue rapprochée."
    tags = []
    obs = []
    for f in exploitable[:3]:
        tags.extend(f.tags)
        obs.extend(f.observations[:2])
    tags = list(dict.fromkeys(tags))
    obs = list(dict.fromkeys(obs))
    return "Photos exploitables : " + "; ".join(obs[:5]) + (f" Tags visuels : {', '.join(tags[:8])}." if tags else "")


def _pathology_signs(facts: ExtractedFacts, retrieved: List[RetrievedSource], findings: Optional[List[ImageFinding]]) -> List[str]:
    signs: List[str] = []
    if facts.mentions_mold_condensation:
        signs.append("Moisissures ponctuelles alléguées ou visibles, à distinguer d'une infiltration active")
    elif facts.mentions_humidity_or_water:
        signs.append("Eau / humidité / infiltration alléguée ou constatée")
    if facts.mentions_crack:
        signs.append("Fissuration ou mouvement signalé")
    if facts.mentions_detachment:
        signs.append("Décollement, soulèvement, arrachement ou risque de chute signalé")
    if facts.mentions_ceiling_suspension:
        signs.append("Suspension ou élément de faux plafond menaçant de tomber")
    for r in retrieved[:3]:
        for s in r.card.signes[:3]:
            if s not in signs:
                signs.append(s)
    for f in (findings or [])[:2]:
        for t in f.tags:
            label = {
                "risque_chute": "Indice visuel de risque de chute à vérifier",
                "eau_humidite": "Indice visuel à rapprocher d'une trace d'humidité ou de moisissure",
                "moisissures_ponctuelles": "Traces ponctuelles compatibles avec des moisissures superficielles",
                "condensation_probable": "Faciès compatible avec condensation / renouvellement d'air insuffisant",
                "fissuration": "Indice visuel orientant vers une fissuration",
                "decollement": "Indice visuel orientant vers un décollement",
                "contraste_defaut_support": "Contraste local pouvant traduire un défaut de support ou de fixation",
            }.get(t)
            if label and label not in signs:
                signs.append(label)
    return signs or ["Symptômes insuffisamment caractérisés dans les pièces reçues"]


def _likely_causes(facts: ExtractedFacts, retrieved: List[RetrievedSource], years: Optional[float]) -> List[str]:
    causes: List[str] = []
    for r in retrieved[:3]:
        for c in r.card.causes_possibles[:4]:
            if c not in causes:
                causes.append(c)
    kind = _maintenance_kind(facts, retrieved)
    if kind == "douche_mastic":
        causes = ["défaut d'entretien caractérisé des mastics souples en périphérie du receveur", "maintien insuffisant en bon état d'usage des joints sanitaires", "infiltration localisée liée à l'usage de la douche"] + causes
    elif kind == "roof_upstand":
        causes = ["défaut d'entretien caractérisé du relevé d'étanchéité / point singulier", "vérification ou maintien insuffisant du bon état des relevés", "reprise localisée d'entretien de toiture-terrasse"] + causes
    if facts.mentions_mold_condensation:
        causes = ["condensation ponctuelle", "déficit local de renouvellement d'air ou VMC à vérifier", "entretien / nettoyage des bouches et entrées d'air à contrôler"] + causes
    if facts.mentions_ceiling_suspension and "défaut de fixation ou de supportage" not in causes:
        causes.insert(0, "défaut de fixation ou de supportage")
    if getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and years is not None and years < 2.0:
        causes = ["apparition dans les deux premières années : défaut constructif à privilégier", "receveur possiblement mal calé ou mobile cisaillant les joints", "défaillance possible du joint du plombier sous le mastic sanitaire"] + causes
    if facts.mentions_detachment and facts.location.startswith("Salle"):
        causes.append("défaut d'adhérence, collage ou support à contrôler")
    if years is not None:
        if years <= 2 and causes:
            causes.append("apparition précoce : défaut constructif initial à privilégier sous réserve des constats")
        elif years >= 8 and facts.mentions_maintenance:
            causes.append("fin de décennale + indice d'entretien/usure : hypothèse à vérifier, sans la retenir automatiquement")
    return list(dict.fromkeys(causes)) or ["Cause non déterminée à ce stade : demander des constats complémentaires ciblés"]


def _impropriete_markers(facts: ExtractedFacts, evidence: Optional[EvidenceAssessment], findings: Optional[List[ImageFinding]]) -> List[str]:
    markers: List[str] = []
    opts = evidence.auto_options if evidence else {}
    if facts.mentions_solidite:
        markers.append("Atteinte possible à la solidité / stabilité à instruire")
    if facts.mentions_mold_condensation:
        markers.append("Moisissures ponctuelles : pas d'impropriété à destination caractérisée à ce stade")
    elif facts.mentions_humidity_or_water and (opts.get("humidity_measured") or opts.get("active_leak") or opts.get("materiality_observed")):
        markers.append("Clos/couvert ou usage normal affecté par eau/humidité objectivée")
    elif facts.mentions_humidity_or_water:
        markers.append("Eau/humidité alléguée : impropriété à confirmer par mesure ou test")
    if facts.mentions_safety or opts.get("visual_safety"):
        markers.append("Risque pour la sécurité des personnes")
    if facts.mentions_impropriete:
        markers.append("Impossibilité ou restriction d'usage alléguée")
    if any("risque_chute" in f.tags for f in (findings or [])):
        markers.append("Photo compatible avec un risque de chute à vérifier")
    return list(dict.fromkeys(markers))


def _severity(facts: ExtractedFacts, element_category: str, markers: List[str], evidence: Optional[EvidenceAssessment]) -> str:
    opts = evidence.auto_options if evidence else {}
    if "ossature" in element_category.lower() or facts.mentions_solidite:
        return "Gravité potentiellement forte : la solidité ou la stabilité doit être instruite par expert senior."
    if any("sécurité" in m.lower() or "chute" in m.lower() for m in markers):
        return "Gravité potentiellement décennale par risque sécurité : l'impropriété tient au risque de chute ou d'atteinte aux personnes, même lorsque l'élément atteint est un équipement dissociable."
    if getattr(facts, "mentions_shower_mastic_maintenance_defect", False):
        yrs = years_since_reception(facts)
        if yrs is not None and yrs < 1.0:
            return "Gravité à instruire, mais déclaration à régulariser : en première année, la DO suppose une mise en demeure GPA restée infructueuse ; ne pas retenir l'entretien des mastics."
        if yrs is not None and yrs < 2.0:
            return "Gravité à instruire : infiltration localisée en périphérie du receveur dans les deux premières années, origine constructive possible même si les conséquences visibles sont limitées."
        return "Gravité décennale non retenue : infiltration localisée en périphérie du receveur, conséquences limitées et rattachables à l'entretien des mastics souples."
    if _is_characterized_maintenance_defect(facts, []):
        return "Gravité décennale non retenue : l'origine déclarée relève d'un défaut d'entretien caractérisé sur un point singulier de toiture-terrasse."
    if facts.mentions_mold_condensation:
        return "Gravité décennale non caractérisée : traces ponctuelles de moisissures sans humidité active, infiltration, généralisation ni perte d'usage objectivée."
    if facts.mentions_humidity_or_water and (opts.get("humidity_measured") or opts.get("active_leak") or opts.get("materiality_observed")):
        return "Gravité potentiellement décennale par atteinte à l'usage normal / clos-couvert, sous réserve du rattachement à l'ouvrage."
    if facts.mentions_humidity_or_water:
        return "Gravité non verrouillée : le récit évoque l'eau, mais il faut objectiver l'humidité, l'infiltration ou la perte d'usage."
    return "Gravité non caractérisée à ce stade : la qualification décennale dépendra des compléments et de l'atteinte réelle à l'usage, à la solidité ou à la sécurité."


def _cause_etrangere(facts: ExtractedFacts, retrieved: List[RetrievedSource], years: Optional[float], evidence: Optional[EvidenceAssessment]) -> str:
    low_ids = {r.card.id for r in retrieved[:4]}
    maintenance_cards = {"VMC_CONDENSATION", "ETANCHEITE_TOITURE_TERRASSE_BALCON", "DOUCHE_ZERO_RESSAUT"}
    if evidence and evidence.auto_options.get("maintenance_neutralized"):
        return "Cause étrangère écartée par élément positif du dossier."
    kind = _maintenance_kind(facts, retrieved)
    if getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and years is not None and years < 2.0:
        if years < 1.0:
            return "Cause étrangère entretien non retenue : première année après réception ; demander la mise en demeure GPA restée infructueuse et rechercher un défaut constructif du receveur ou des barrières d'étanchéité."
        return "Cause étrangère entretien non retenue : dans les deux premières années, une infiltration périphérique peut révéler un défaut constructif de calage du receveur ou une défaillance des barrières d'étanchéité."
    if kind == "douche_mastic":
        return "Défaut d'entretien caractérisé : le maintien en bon état d'usage des mastics souples en périphérie du receveur relève de l'entretien normal du logement."
    if kind == "roof_upstand":
        return "Défaut d'entretien caractérisé : la vérification et le maintien du bon état des relevés d'étanchéité relèvent de l'entretien dû par la copropriété."
    if facts.mentions_maintenance and (low_ids & maintenance_cards):
        time_note = ""
        if years is not None and years >= 8:
            time_note = " Le sinistre étant en fin de décennale, la vérification entretien/usure est pertinente, mais seulement à partir d'indices concrets."
        return "Cause étrangère à vérifier et à nommer : entretien / usage / usure, car une fiche entretien applicable et un indice concret sont présents." + time_note
    if facts.mentions_maintenance:
        return "Indice d'entretien/usure/usage détecté, mais il doit être rattaché à une fiche et à un fait concret avant d'être invoqué."
    if facts.mentions_mold_condensation and any(r.card.id in maintenance_cards for r in retrieved[:4]):
        return "Entretien / ventilation à vérifier : la fiche ventilation-entretien est pertinente, mais l'orientation principale reste l'absence de gravité décennale si les traces sont ponctuelles."
    if any(r.card.id in maintenance_cards for r in retrieved[:4]):
        return "Aucune cause étrangère concrète détectée : ne pas invoquer l'entretien au seul motif qu'une fiche entretien existe."
    return "Aucune cause étrangère pertinente détectée dans les éléments reçus."


def _guarantee_analysis(decision: DecisionResult, element_category: str, markers: List[str]) -> str:
    if decision.decision_code == "DECLARATION_NON_CONSTITUEE_GPA":
        return "Garantie obligatoire non mobilisable en l'état : première année après réception, mise en demeure de l'entrepreneur au titre de la GPA et preuve de son infructuosité à demander avant mobilisation DO."
    if decision.decision_code.startswith("REFUS"):
        if "joints de douche" in decision.decision_label.lower() or "mastic" in decision.decision_label.lower():
            return "Garantie obligatoire non mobilisable proposée : le fait caractérisé relève du maintien en bon état d'usage des mastics souples et joints sanitaires en périphérie du receveur."
        if "défaut d'entretien" in decision.decision_label.lower() or "entretien toiture" in decision.decision_label.lower():
            return "Garantie obligatoire non mobilisable proposée : le fait caractérisé relève de la vérification et du maintien en bon état des relevés d'étanchéité, donc de l'entretien dû par la copropriété."
        if "moisiss" in decision.decision_label.lower() or "ventilation" in decision.decision_label.lower():
            return "Garantie obligatoire non mobilisable proposée : traces de moisissures ponctuelles sans atteinte à la solidité ni impropriété à destination objectivée ; orientation entretien / ventilation."
        return "Garantie obligatoire non mobilisable proposée : absence de gravité décennale objectivée ou contexte de non-conformité / travaux non terminés, sous réserve de validation humaine."
    if decision.decision_code.startswith("GARANTIE"):
        basis = " ; ".join(markers) if markers else "faisceau de gravité à valider"
        return f"Garantie obligatoire possible/acquise sous contrôle humain : {basis}. L'analyse tient compte de l'élément affecté ({element_category}) et du quantum sous TM."
    if decision.decision_code == "ESCALADE_SENIOR":
        return "Aucune position automatique ferme : risque structurel, sécurité ou incertitude technique nécessitant une analyse expert senior."
    return "Position de garantie non verrouillée : compléments nécessaires avant décision."


def _repair_principle(facts: ExtractedFacts, retrieved: List[RetrievedSource], decision: DecisionResult) -> str:
    if decision.pricing.get("method"):
        pricing = decision.pricing.get("details", "")
    else:
        pricing = "Chiffrage non disponible."
    kind = _maintenance_kind(facts, retrieved)
    if kind == "douche_mastic":
        return "Reprise d'entretien des joints/mastics périphériques du receveur, après nettoyage et assèchement des conséquences ponctuelles en pied de cloison. Pas d'indemnité DO proposée. " + pricing
    if kind == "roof_upstand":
        return "Faire reprendre le relevé d'étanchéité / point singulier dans le cadre de l'entretien de la toiture-terrasse par la copropriété ; vérifier les autres relevés, solins et évacuations accessibles. Pas d'indemnité DO proposée. " + pricing
    if facts.mentions_ceiling_suspension:
        return "Contacter prioritairement l'électricien d'origine / l'entreprise du lot électricité pour vérifier une intervention spontanée compte tenu du défaut de fixation visible et du coût modeste. À défaut : sécurisation, dépose-repose du luminaire, reprise correcte des fixations, rebouchage/enduit et reprise ponctuelle de peinture du faux plafond. " + pricing
    if facts.mentions_mold_condensation:
        return "Nettoyage ponctuel des traces à l'eau légèrement javellisée, puis contrôle/entretien des bouches, entrées d'air et débits VMC. Pas de réparation décennale identifiée à ce stade. " + pricing
    if getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False):
        yrs = years_since_reception(facts)
        if yrs is not None and yrs < 2.0:
            return "Réparation à définir après vérification du calage/stabilité du receveur, du joint du plombier, de la mise en eau et de l'étendue des conséquences. Ne pas limiter la réponse à une reprise d'entretien des mastics. " + pricing
    if facts.mentions_humidity_or_water:
        return "Réparation à définir après objectivation de l'origine : traitement de l'étanchéité, du joint, du réseau ou du support, puis reprise des conséquences après assèchement. " + pricing
    if facts.mentions_detachment:
        return "Réparation à calibrer selon l'ampleur : sondage des zones qui sonnent creux ou menacent de tomber, dépose des parties non adhérentes, reprise support/collage et finitions. " + pricing
    return "Mode réparatoire à préciser après identification de l'élément affecté, de l'étendue et des causes. " + pricing


def _analysed_damage(facts: ExtractedFacts, retrieved: List[RetrievedSource], element_category: str) -> str:
    declared = facts.declared_damage or "Dommage non libellé"
    kind = _maintenance_kind(facts, retrieved)
    if kind == "douche_mastic":
        return "Infiltrations localisées en périphérie du receveur, avec légères conséquences en pied de cloison : défaut d'entretien des mastics souples à privilégier."
    if kind == "roof_upstand":
        return "Infiltration alléguée depuis une toiture-terrasse, avec relevé d'étanchéité décollé/dégradé déclaré par le mainteneur : défaut d'entretien caractérisé à privilégier."
    yrs = years_since_reception(facts)
    if getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and yrs is not None and yrs < 2.0:
        return "Infiltration en périphérie du receveur en début de période : défaut constructif à instruire en priorité ; entretien des mastics non retenu à ce stade."
    if facts.mentions_mold_condensation:
        return "Traces de moisissures ponctuelles dans une chambre, compatibles avec un phénomène de condensation localisé / ventilation à vérifier."
    if facts.mentions_ceiling_suspension:
        return "Luminaire décoratif qui se décroche de son support en faux plafond, avec risque potentiel de chute."
    if facts.mentions_detachment and _is_top(retrieved, {"FAIENCE_MURALE_SECURITE", "CARRELAGE_SOL"}):
        return "Décollement de revêtement carrelé/faïence, avec risque de chute ou perte d'usage à apprécier selon l'étendue."
    if facts.mentions_humidity_or_water and _is_top(retrieved, {"DOUCHE_ZERO_RESSAUT", "PLOMBERIE_RESEAUX"}):
        return "Humidité / infiltration en local humide ou au droit d'un réseau, origine à rattacher à l'étanchéité, aux joints ou aux traversées."
    if len(declared) <= 220:
        return declared
    return declared[:217] + "..."


def build_expertal_analysis(
    facts: ExtractedFacts,
    retrieved: List[RetrievedSource],
    decision: DecisionResult,
    raw_text: str = "",
    evidence: Optional[EvidenceAssessment] = None,
    image_findings: Optional[List[ImageFinding]] = None,
) -> ExpertalAnalysis:
    years = years_since_reception(facts)
    method = assess_methodology(facts, retrieved, raw_text)
    decade_year, chrono_note = _year_label(years)
    element_category, element_detail = _affected_element(facts, retrieved)
    if decision.decision_code == "ESS_NECESSAIRE_TOITURE" or _is_top_floor_roof_leak(facts, raw_text):
        element_category = "Clos-couvert / toiture / terrasse technique à visualiser"
        element_detail = "Ouvrages surmontant le plafond du dernier étage : toiture, terrasse technique, édicule, relevés, évacuations EP, traversées et équipements techniques."
    elif method.defaut_entretien_caracterise:
        element_category = method.corps_etat
        element_detail = method.element_affecte
    analysed = _analysed_damage(facts, retrieved, element_category)
    if decision.decision_code == "ESS_NECESSAIRE_TOITURE" or _is_top_floor_roof_leak(facts, raw_text):
        analysed = "Fuite / résurgence en plafond du dernier étage, potentiellement liée au clos-couvert, avec origine toiture/terrasse technique non visualisée."
    visual = _visual_context(image_findings, facts)
    signs = _pathology_signs(facts, retrieved, image_findings)
    causes = _likely_causes(facts, retrieved, years)
    markers = _impropriete_markers(facts, evidence, image_findings)
    severity = _severity(facts, element_category, markers, evidence)
    ce = _cause_etrangere(facts, retrieved, years, evidence)
    guarantee = _guarantee_analysis(decision, element_category, markers)
    repair = _repair_principle(facts, retrieved, decision)
    if decision.decision_code == "ESS_NECESSAIRE_TOITURE" or _is_top_floor_roof_leak(facts, raw_text):
        severity = "Désordre à caractère potentiellement décennal par fuite en plafond d'un logement au dernier étage, mais avis non motivable sans constat des ouvrages supérieurs."
        ce = "CE-X : cause étrangère non documentée / non neutralisée. Entretien, obstruction d'évacuation, défaut de relevé/solin, équipement technique ou intervention tierce doivent être vérifiés sur toiture/terrasse technique."
        guarantee = "Les désordres observés peuvent revêtir un caractère décennal, mais il est nécessaire de visualiser les ouvrages surmontant le plafond du logement stigmatisé pour émettre un avis motivé. À défaut de pièces complémentaires, bascule en ESS."
        repair = "Aucun mode réparatoire ni chiffrage DO ne doit être proposé avant identification de l'origine. Demander les pièces ciblées ou organiser une expertise sur site."
    pricing_comment = decision.pricing.get("details", "") if decision.pricing else ""

    elements_to_obtain: List[str] = []
    if evidence:
        elements_to_obtain.extend(evidence.missing)
        elements_to_obtain.extend(evidence.to_verify)
    if not facts.construction_type or facts.construction_type == "Non déterminé":
        elements_to_obtain.append("Type d'ouvrage assuré / description de l'opération à confirmer depuis la police DO")
    if "Non déterminé" in (facts.location or ""):
        elements_to_obtain.append("Localisation précise : pièce, zone, intérieur/extérieur, partie privative/commune")
    if not image_findings:
        elements_to_obtain.append("Photos : vue d'ensemble + vue rapprochée + échelle ou repère dimensionnel")
    if decision.decision_code == "ESS_NECESSAIRE_TOITURE" or _is_top_floor_roof_leak(facts, raw_text):
        elements_to_obtain.extend([
            "Photos de la toiture / terrasse technique / édicule au-dessus du plafond concerné",
            "Photos rapprochées des relevés, solins, évacuations EP, traversées et équipements techniques",
            "Plan de toiture ou plan de niveau annoté avec localisation du logement et de la trace en plafond",
            "Contrat d'entretien de la terrasse technique / toiture et périmètre de maintenance",
            "Dernier compte-rendu de visite du mainteneur avec avis technique sur le problème",
            "Recherche de fuite ou test d'arrosage ciblé si l'origine reste incertaine",
        ])

    construction_context = facts.construction_type or "Non déterminé"
    if construction_context == "Non déterminé":
        construction_context += " — l'application doit rechercher la police DO ou la description de l'opération pour se mettre dans le bon contexte technique."

    reasoning_path = [
        "0. Croisement méthodologique : " + method.corps_etat + " / " + method.pathologie + " / fiche " + method.fiche_principale,
        "0bis. Entretien : " + ("défaut caractérisé - " + method.entretien_rationale if method.defaut_entretien_caracterise else "non retenu sans fait concret"),
        "1. Reprendre le dommage déclaré tel qu'écrit puis le résumer si nécessaire.",
        f"2. Situer le sinistre dans le temps : {decade_year}. {chrono_note}",
        f"3. Identifier le type d'ouvrage : {construction_context}.",
        f"4. Situer la zone et le local : {_zone_context(facts)}",
        f"5. Lire les photos et les confronter à la déclaration : {visual}",
        "6. Relever les signes visibles et les rapprocher des pathologies connues.",
        f"7. Identifier l'élément affecté : {element_category} — {element_detail}",
        f"8. Apprécier solidité / impropriété / sécurité : {severity}",
        f"9. Rechercher uniquement les causes étrangères pertinentes et nommées : {ce}",
        f"10. En déduire la garantie et le mode réparatoire : {guarantee}",
    ]

    return ExpertalAnalysis(
        declared_damage=facts.declared_damage or "Non extrait",
        analysed_damage=analysed,
        chronology=chrono_note,
        decade_year=decade_year,
        construction_context=construction_context,
        location_context=_zone_context(facts),
        visual_context=visual,
        affected_element_category=element_category,
        affected_element_detail=element_detail,
        pathology_signs=signs,
        likely_causes=causes,
        severity_assessment=severity,
        impropriete_markers=markers or ["Aucun marqueur d'impropriété suffisamment objectivé à ce stade"],
        cause_etrangere_screening=ce,
        guarantee_analysis=guarantee,
        repair_principle=repair,
        pricing_comment=pricing_comment,
        elements_to_obtain=list(dict.fromkeys(elements_to_obtain)),
        reasoning_path=reasoning_path,
    )
