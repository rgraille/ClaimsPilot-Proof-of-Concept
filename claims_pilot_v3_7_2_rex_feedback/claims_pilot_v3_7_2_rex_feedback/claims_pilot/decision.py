from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from .extractor import ExtractedFacts
from .retrieval import RetrievedSource
from .pricing import PricingResult, estimate_simple_pricing
from .methodology import assess_methodology

TM_TTC = 1960.0


@dataclass
class DecisionResult:
    decision_code: str
    decision_label: str
    garantie_score: int
    quantum_score: int
    robustesse_globale: int
    niveau_validation: str
    sortie_decennalite: str
    cause_etrangere: str
    force_probatoire: str
    tva_rate: float
    tm_ttc: float
    tm_ht: float
    montant_ttc: float | None
    ecart_tm: float | None
    red_flags: List[str]
    complements: List[str]
    reasons: List[str]
    pricing: Dict[str, Any]
    montant_estime: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def years_since_reception(facts: ExtractedFacts) -> Optional[float]:
    d1 = _parse_date(facts.reception_date)
    d2 = _parse_date(facts.declaration_date) or _parse_date(facts.loss_date)
    # En démo, beaucoup de déclarations collées ne comportent pas la date du mail.
    # On utilise alors la date du jour pour situer prudemment le dossier dans la décennale,
    # tout en laissant la date d'apparition comme élément manquant dans la complétude.
    if d1 and not d2:
        d2 = datetime.today()
    if not d1 or not d2:
        return None
    return max(0.0, (d2 - d1).days / 365.25)




def _is_gpa_period(facts: ExtractedFacts) -> bool:
    yrs = years_since_reception(facts)
    return bool(yrs is not None and yrs < 1.0)

def _is_first_two_years(facts: ExtractedFacts) -> bool:
    yrs = years_since_reception(facts)
    return bool(yrs is not None and yrs < 2.0)

def _has_gpa_formal_notice(raw_text: str) -> bool:
    low = (raw_text or "").lower()
    return ("mise en demeure" in low and ("infruct" in low or "restée infructueuse" in low or "restee infructueuse" in low or "sans effet" in low)) or ("gpa" in low and "mise en demeure" in low)

def infer_vat_rate(facts: ExtractedFacts, forced_rate: float | None = None) -> float:
    if forced_rate in (0.10, 0.20):
        return forced_rate
    yrs = years_since_reception(facts)
    # Les interventions de dépannage/réparation d'équipement PAC/chauffage sont souvent devisées à 20% ;
    # si un devis indique déjà un TTC, ce taux sert surtout à l'affichage HT/TTC.
    if getattr(facts, "mentions_heating_pac", False) or getattr(facts, "mentions_refrigerant_leak", False):
        return 0.20
    if facts.construction_type in ("Bâtiment collectif d'habitation", "Maison individuelle") and yrs is not None and yrs >= 2:
        return 0.10
    return 0.20


def _has_card(retrieved: List[RetrievedSource], card_id: str, limit: int = 5) -> bool:
    return any(r.card.id == card_id for r in retrieved[:limit])


def _maintenance_kind(facts: ExtractedFacts, retrieved: List[RetrievedSource], raw_text: str = "") -> str:
    """Type de défaut d'entretien caractérisé, issu du croisement corps d'état/pathologie/fiche entretien."""
    method = assess_methodology(facts, retrieved, raw_text)
    if method.entretien_kind in {"chauffage_pac_gbf_forclos"}:
        return method.entretien_kind
    return method.entretien_kind if method.defaut_entretien_caracterise else ""


def _is_characterized_maintenance_defect(facts: ExtractedFacts, retrieved: List[RetrievedSource], raw_text: str = "") -> bool:
    """Défaut d'entretien invocable uniquement si un fait concret l'objective."""
    return bool(_maintenance_kind(facts, retrieved, raw_text))






def _is_living_ceiling_terrace_trace_nondec(facts: ExtractedFacts, raw_text: str) -> bool:
    low = ((raw_text or "") + " " + (getattr(facts, "declared_damage", "") or "") + " " + (getattr(facts, "location", "") or "")).lower()
    context = bool(getattr(facts, "mentions_living_ceiling_under_terrace_trace", False) or ("plafond" in low and ("séjour" in low or "sejour" in low or "salon" in low) and ("trace" in low or "infiltration" in low or "auréole" in low or "aureole" in low)))
    active = bool(getattr(facts, "mentions_active_infiltration", False) or any(k in low for k in ["écoulement", "ecoulement", "ruissellement", "humidité active", "humidite active", "goutte à goutte", "goutte a goutte"]))
    interior_entry = bool(getattr(facts, "mentions_interior_water_ingress", False))
    extensive = any(k in low for k in ["plafond effondré", "plafond effondre", "généralis", "generalis", "plusieurs pièces", "plusieurs pieces", "inhabitable", "impossible d'occuper"])
    dry_or_no_resurgence = bool(getattr(facts, "mentions_dry_inactive_trace", False) or getattr(facts, "mentions_no_facade_resurgence", False) or not active)
    return bool(context and dry_or_no_resurgence and not active and not interior_entry and not extensive)

def _is_loggia_roof_non_decennial(facts: ExtractedFacts, raw_text: str) -> bool:
    low = ((raw_text or "") + " " + (getattr(facts, "declared_damage", "") or "") + " " + (getattr(facts, "location", "") or "")).lower()
    loggia = "loggia" in low or "balcon" in low
    roof = "toiture" in low or "couverture" in low or "étanchéité" in low or "etancheite" in low
    trace = any(k in low for k in ["auréole", "aureole", "trace", "infiltration", "dégât des eaux", "degat des eaux", "plafond"])
    interior = any(k in low for k in ["chambre", "salon", "séjour", "sejour", "cuisine", "pièce habitable", "piece habitable", "entrée d'eau dans le logement", "entree d'eau dans le logement", "intérieur du logement", "interieur du logement"])
    return bool(loggia and roof and trace and not interior)

def _is_top_floor_roof_leak(facts: ExtractedFacts, raw_text: str) -> bool:
    low = (raw_text or "").lower()
    damage = (getattr(facts, "declared_damage", "") or "").lower()
    return bool(
        ("fuite" in low or "infiltration" in low or "humid" in low)
        and ("plafond du dernier" in low or "dernier étage" in low or "dernier etage" in low or "plafond du dernier" in damage)
        and ("toiture" in low or "terrasse technique" in low or "édicule" in low or "edicule" in low or "dernier étage" in low or "dernier etage" in low)
    )

def _cause_etrangere_label(facts: ExtractedFacts, mode_options: Dict[str, bool], retrieved: List[RetrievedSource], raw_text: str = "") -> str:
    """CE jamais abstraite ; entretien retenu si une fiche et un défaut caractérisé sont présents."""
    if _is_living_ceiling_terrace_trace_nondec(facts, raw_text):
        return "Cause étrangère / entretien à vérifier : possible entretien de terrasse supérieure ou point singulier localisé ; le seuil décennal n'est pas atteint faute d'infiltration active objectivée"
    if _is_loggia_roof_non_decennial(facts, raw_text):
        return "Cause étrangère non déterminante à ce stade : le seuil décennal n'est pas atteint faute d'entrée d'eau dans le logement ou d'impropriété objectivée"
    if _is_top_floor_roof_leak(facts, raw_text):
        return "CE-X - Cause étrangère non documentée / non neutralisée : visualiser la toiture, la terrasse technique, les relevés, évacuations EP et équipements surmontant le plafond avant avis motivé"
    if mode_options.get("maintenance_neutralized", False):
        return "Aucune cause étrangère pertinente identifiée ou entretien/usage écarté par les éléments reçus"
    method = assess_methodology(facts, retrieved, raw_text)
    kind = method.entretien_kind if (method.defaut_entretien_caracterise or method.entretien_kind == "chauffage_pac_gbf_forclos") else ""
    if kind == "chauffage_pac_gbf_forclos":
        return "Hors cause étrangère utile : le dommage relève d'un élément d'équipement de chauffage / PAC, soumis à la garantie de bon fonctionnement forclose, sans impropriété décennale objectivée"
    if method.fiche_entretien_applicable and _is_first_two_years(facts) and not kind:
        if _is_gpa_period(facts) and not _has_gpa_formal_notice(raw_text):
            return "Aucune cause étrangère entretien non retenue : première année après réception, mise en demeure GPA restée infructueuse à demander avant mobilisation DO"
        return "Aucune cause étrangère entretien non retenue : dans les deux premières années, l'usure normale est peu vraisemblable ; rechercher d'abord une origine constructive ou une défaillance initiale"
    if kind == "douche_mastic":
        return "CE3 - Défaut d'entretien caractérisé : le maintien en bon état d'usage des mastics souples en périphérie du receveur relève de l'entretien normal du logement"
    if kind == "roof_upstand":
        return "CE3 - Défaut d'entretien caractérisé : la vérification et le maintien du bon état des relevés d'étanchéité relèvent de l'entretien dû par la copropriété"
    if kind == "plomberie_piece_usure":
        return "CE3 - Défaut d'entretien caractérisé : l'organe de plomberie localisé relève de l'entretien/remplacement d'une pièce d'usure"
    if facts.mentions_maintenance:
        return "CE1 - Cause étrangère à vérifier et à nommer : entretien / usage / usure / maintenance"
    if any(r.card.id in {"VMC_CONDENSATION", "ETANCHEITE_TOITURE_TERRASSE_BALCON", "DOUCHE_ZERO_RESSAUT"} for r in retrieved[:3]):
        return "Aucune cause étrangère concrète détectée ; ne pas l'invoquer sans indice d'entretien, obstruction, usage ou intervention tierce"
    return "Aucune cause étrangère pertinente détectée dans les éléments reçus"

def decide(facts: ExtractedFacts, retrieved: List[RetrievedSource], mode_options: Dict[str, bool] | None = None, forced_vat: float | None = None, raw_text: str = "") -> DecisionResult:
    mode_options = mode_options or {}
    materiality = mode_options.get("materiality_observed", False)
    humidity_measured = mode_options.get("humidity_measured", False)
    active_leak = mode_options.get("active_leak", False)
    photos_exploitable = mode_options.get("photos_exploitable", facts.has_photos)
    senior_sensitive = mode_options.get("senior_sensitive", False)
    visual_safety = mode_options.get("visual_safety", False)

    reasons: List[str] = []
    complements: List[str] = []
    red_flags: List[str] = []

    method = assess_methodology(facts, retrieved, raw_text)
    first_year_gpa = _is_gpa_period(facts)
    first_two_years = _is_first_two_years(facts)
    shower_first_two_years = bool(getattr(facts, "mentions_shower_receiver", False) and getattr(facts, "mentions_shower_peripheral_joint", False) and first_two_years)
    normal_wear_first_two_years = bool(method.fiche_entretien_applicable and first_two_years and not method.defaut_entretien_caracterise)
    gpa_formal_notice = _has_gpa_formal_notice(raw_text)
    reasons.append("Démarche expertale : dommage déclaré → corps d'état → pathologie → fiche métier → fiche entretien éventuelle → âge du sinistre → gravité décennale.")
    reasons.append(f"Croisement retenu : {method.corps_etat} / {method.pathologie} / fiche {method.fiche_principale}.")
    if method.fiche_entretien_applicable and method.defaut_entretien_caracterise:
        reasons.append(method.entretien_rationale)
    elif method.fiche_entretien_applicable:
        complements.append("Fiche entretien applicable mais défaut non suffisamment caractérisé : compléter les constats avant de l'invoquer.")
    complements.extend(method.complements[:3])

    vat = infer_vat_rate(facts, forced_vat)
    pricing: PricingResult = estimate_simple_pricing(facts, raw_text, retrieved, vat)
    amount_ttc = pricing.amount_ttc
    amount_estimated = pricing.source == "estimation_simple"

    if facts.has_prior_intervention:
        red_flags.append("Antécédent ou intervention antérieure mentionné")
    if facts.mentions_humidity_or_water and not facts.mentions_mold_condensation:
        red_flags.append("Pathologie liée à l'eau")
    if _is_living_ceiling_terrace_trace_nondec(facts, raw_text):
        red_flags.append("Trace ponctuelle plafond séjour : matérialité d'infiltration active non objectivée")
    if _is_loggia_roof_non_decennial(facts, raw_text):
        red_flags.append("Trace en loggia / extérieur privatif : seuil décennal non caractérisé")
    if _is_top_floor_roof_leak(facts, raw_text):
        red_flags.append("Fuite plafond dernier étage : ouvrages supérieurs / toiture à visualiser")
        red_flags.append("Cause étrangère toiture non neutralisée")
    if facts.mentions_mold_condensation:
        red_flags.append("Moisissures ponctuelles / ventilation à vérifier")
    if (facts.mentions_safety or visual_safety) and not getattr(facts, "mentions_refrigerant_leak", False):
        red_flags.append("Sécurité / risque de chute à vérifier")
    if facts.mentions_solidite:
        red_flags.append("Solidité / structure à vérifier")
    if facts.mentions_reserve_or_gpa:
        red_flags.append("Réserve / GPA / travaux non terminés possibles")
    if facts.mentions_ceiling_suspension:
        red_flags.append("Élément suspendu en plafond : mesure conservatoire possible")
    if senior_sensitive:
        red_flags.append("Sensibilité technique déclarée ou détectée")
    if amount_ttc is not None and amount_ttc >= TM_TTC * 0.8 and amount_ttc < TM_TTC:
        red_flags.append("Quantum proche du ticket modérateur")
    maintenance_kind = _maintenance_kind(facts, retrieved, raw_text)
    if maintenance_kind:
        if maintenance_kind == "chauffage_pac_gbf_forclos":
            red_flags.append("Chauffage / PAC : garantie de bon fonctionnement possiblement forclose")
        else:
            red_flags.append("Défaut d'entretien caractérisé par croisement corps d'état / pathologie / fiche entretien")

    if not photos_exploitable:
        complements.append("Photos exploitables du désordre et de son environnement")
    if _is_living_ceiling_terrace_trace_nondec(facts, raw_text):
        complements.extend([
            "Compte rendu de passage de la société chargée de l'entretien de la terrasse supérieure",
            "Photos de la terrasse supérieure : mousse, bande solin, joint de fractionnement, tête de relevé, évacuations",
            "Confirmer que la trace est sèche/apathique et non évolutive",
            "Confirmer l'absence d'eau active et d'entrée d'eau dans le séjour",
        ])
    if _is_loggia_roof_non_decennial(facts, raw_text):
        complements.extend([
            "Confirmer que les auréoles sont limitées à la loggia et qu'aucune pièce habitable n'est affectée",
            "Photo de loin situant la loggia par rapport au logement",
            "Photo intérieure du logement au droit de la loggia si contestation",
            "Date d'apparition et évolution des auréoles",
        ])
    if _is_top_floor_roof_leak(facts, raw_text):
        complements.extend([
            "Photos de la toiture / terrasse technique / édicule au-dessus du plafond stigmatisé",
            "Plan de toiture ou plan de niveau annoté avec localisation du logement et de la trace en plafond",
            "Contrat d'entretien de la terrasse technique / toiture et périmètre de maintenance",
            "Dernier compte-rendu de visite du mainteneur avec avis sur l'origine possible",
            "Photos rapprochées des relevés, solins, évacuations EP, traversées et équipements techniques",
            "Recherche de fuite ou test d'arrosage ciblé si l'origine reste incertaine",
        ])
    if getattr(facts, "mentions_refrigerant_leak", False):
        complements.append("Rapport chauffagiste / mainteneur PAC, localisation du raccord fuyard, devis de réparation et état de fonctionnement chauffage/ECS")
    elif facts.mentions_mold_condensation and not (humidity_measured or active_leak):
        complements.append("Contrôler le fonctionnement de la VMC / les débits, les bouches et entrées d'air ; vérifier l'absence d'évolution ou d'humidité active")
    elif facts.mentions_humidity_or_water and not (humidity_measured or active_leak):
        complements.append("Objectivation de l'humidité / fuite : humidimètre, test d'arrosage ou recherche de fuite")
    if facts.mentions_ceiling_suspension:
        complements.append("Vérifier le mode de fixation, le support réel et l'existence d'autres suspensions identiques")
    if not facts.reception_date:
        complements.append("Date de réception / PV de réception")
    if not facts.declaration_date and not facts.loss_date:
        complements.append("Date de survenance ou de déclaration")
    if amount_ttc is None and not facts.mentions_mold_condensation:
        complements.append("Devis, métrés ou estimation simple paramétrée des réparations")
    elif amount_estimated:
        complements.append("Valider humainement l'estimation simple : heures retenues, TVA, périmètre de réparation")

    garantie_score = 35
    if facts.reception_date:
        garantie_score += 10
    if facts.location != "Non déterminé":
        garantie_score += 8
    if retrieved:
        garantie_score += min(15, int(sum(r.score for r in retrieved[:3]) / 2))
    if facts.has_photos or photos_exploitable:
        garantie_score += 8
    if materiality:
        garantie_score += 15
        reasons.append("Matérialité objectivée par constat, mesure ou analyse visuelle exploitable")
    if humidity_measured or active_leak:
        garantie_score += 10
        reasons.append("Symptôme eau/humidité objectivé")
    if facts.mentions_mold_condensation and not (humidity_measured or active_leak):
        garantie_score += 4
        reasons.append("Moisissures ponctuelles déclarées/visibles : matérialité possible mais gravité décennale non caractérisée en l'absence d'infiltration ou d'humidité active")
    if (facts.mentions_safety or visual_safety) and not getattr(facts, "mentions_refrigerant_leak", False):
        garantie_score += 12
        reasons.append("Risque sécurité / chute identifié comme marqueur de gravité à vérifier")
    if facts.mentions_solidite or facts.mentions_impropriete:
        garantie_score += 5
    if facts.mentions_reserve_or_gpa:
        garantie_score -= 12
    if facts.mentions_maintenance and not mode_options.get("maintenance_neutralized", False) and not normal_wear_first_two_years:
        garantie_score -= 8
    if normal_wear_first_two_years:
        reasons.append("Dossier dans les deux premières années avec fiche entretien possible : ne pas retenir l'usure normale comme cause dominante sans preuve forte ; rechercher une origine constructive, de pose, réglage, calage ou qualité initiale.")
        if first_year_gpa and not gpa_formal_notice:
            garantie_score -= 18
            complements.append("Première année après réception : demander la mise en demeure de l'entrepreneur au titre de la garantie de parfait achèvement et la preuve de son caractère infructueux.")
    if maintenance_kind:
        if maintenance_kind == "chauffage_pac_gbf_forclos":
            reasons.append("Le dossier relève d'une analyse équipement de chauffage / garantie de bon fonctionnement : non-décennalité robuste si aucune impropriété de l'ouvrage dans son ensemble n'est objectivée.")
        else:
            garantie_score -= 22
            reasons.append("Défaut d'entretien caractérisé par les éléments reçus : la cause étrangère n'est pas seulement à vérifier, elle peut fonder une orientation de non-garantie")
    garantie_score = max(0, min(100, garantie_score))

    quantum_score = 25
    if amount_ttc is not None:
        quantum_score += 35 if amount_estimated else 40
        reasons.append(f"Montant {'estimé' if amount_estimated else 'identifié'} : {amount_ttc:,.2f} € TTC".replace(",", " "))
        reasons.append(pricing.details)
    if pricing.source == "extrait":
        quantum_score += 20 if facts.has_quote else 10
    elif pricing.source == "estimation_simple":
        quantum_score += 18
    if retrieved:
        quantum_score += 5
    if amount_ttc is not None and amount_ttc < TM_TTC:
        quantum_score += 10
    if amount_ttc is not None and amount_ttc >= TM_TTC * 0.8:
        quantum_score -= 12
    quantum_score = max(0, min(100, quantum_score))

    if _is_living_ceiling_terrace_trace_nondec(facts, raw_text):
        garantie_score = max(garantie_score, 86)
        quantum_score = max(quantum_score, 70 if amount_ttc is not None else 55)
        reasons.append("Trace ponctuelle en plafond du séjour sous terrasse supérieure : la matérialité d'une infiltration active n'est pas objectivée ; le caractère décennal n'est pas caractérisé en l'état.")
        reasons.append("À réouvrir si une venue d'eau active, une évolution de la trace, une résurgence en façade ou une contrariété d'occupation du logement est objectivée.")
    if _is_loggia_roof_non_decennial(facts, raw_text):
        garantie_score = max(garantie_score, 82)
        quantum_score = max(quantum_score, 30)
        reasons.append("Loggia / extérieur privatif : les éléments reçus permettent de supposer l'absence d'entrée d'eau dans le logement ; le caractère décennal n'est pas caractérisé.")
        reasons.append("À réouvrir seulement si une entrée d'eau en local habitable, une évolution significative ou une impropriété d'usage est objectivée.")
    if _is_top_floor_roof_leak(facts, raw_text):
        garantie_score = min(garantie_score, 62)
        quantum_score = min(quantum_score, 25)
        reasons.append("Résurgence en plafond du dernier étage : le désordre observé est potentiellement décennal, mais la cause étrangère toiture/terrasse technique n'est pas neutralisée.")
        reasons.append("Avis garantie non motivable sans visualisation des ouvrages surmontant le plafond concerné.")
    top_ids = {r.card.id for r in retrieved[:3]}
    non_garantie_context = bool(top_ids & {"NON_CONFORMITE_RESSAUT_RESERVE"}) or facts.mentions_reserve_or_gpa
    mold_condensation_context = facts.mentions_mold_condensation
    water_context = ((facts.mentions_humidity_or_water and not facts.mentions_mold_condensation) or bool(top_ids & {"DOUCHE_ZERO_RESSAUT", "PLOMBERIE_RESEAUX", "ETANCHEITE_TOITURE_TERRASSE_BALCON", "FACADE_INFILTRATION"})) and not getattr(facts, "mentions_refrigerant_leak", False)
    safety_ceiling_context = facts.mentions_ceiling_suspension or _has_card(retrieved, "SUSPENSION_FAUX_PLAFOND_SECURITE") or visual_safety
    characterized_maintenance_context = bool(maintenance_kind)

    if _is_living_ceiling_terrace_trace_nondec(facts, raw_text):
        decision_code = "REFUS_GARANTIE_PROPOSE_TRACE_SECHE"
        decision_label = "Non-garantie proposée - trace sèche ponctuelle en plafond du séjour"
        sortie = "D1 - Non décennal probable / matérialité d'infiltration active non objectivée"
        reasons.append("Les photos et le contexte déclaratif orientent vers une trace très ponctuelle et apparemment sèche/apathique, sans résurgence de façade objectivée et sans contrariété d'occupation du logement.")
        reasons.append("La garantie DO obligatoire n'est pas mobilisable en l'état ; demander seulement les éléments permettant de confirmer l'absence de défaut d'étanchéité actif / entretien terrasse.")
    elif _is_loggia_roof_non_decennial(facts, raw_text):
        decision_code = "REFUS_GARANTIE_PROPOSE_LOGGIA"
        decision_label = "Non-garantie proposée - traces en loggia sans entrée d'eau dans le logement"
        sortie = "D1 - Non décennal probable / absence d'impropriété objectivée"
        reasons.append("Le dommage déclaré est localisé en loggia ; les photos montrent des auréoles / traces en plafond de loggia, sans élément attestant une entrée d'eau dans une pièce habitable.")
        reasons.append("L'origine toiture peut être vérifiée si nécessaire, mais l'absence d'atteinte au logement ou à l'usage normal neutralise la gravité décennale à ce stade.")
    elif _is_top_floor_roof_leak(facts, raw_text):
        decision_code = "ESS_NECESSAIRE_TOITURE"
        decision_label = "ESS nécessaire - fuite plafond dernier étage / ouvrages surmontants à visualiser"
        sortie = "D3 - Décennalité possible à instruire, CE-X non neutralisée"
        reasons.append("Basculer en expertise sur site si le déclarant ne peut pas fournir les éléments ciblés permettant d'identifier l'origine et d'écarter entretien, obstruction ou intervention tierce.")
    elif first_year_gpa and not gpa_formal_notice:
        decision_code = "DECLARATION_NON_CONSTITUEE_GPA"
        decision_label = "Déclaration non constituée - mise en demeure GPA à demander"
        sortie = "D0 - Première année / GPA préalable"
        reasons.append("Sinistre déclaré pendant la première année suivant la réception : la DO ne peut être mobilisée qu'après mise en demeure de l'entrepreneur restée infructueuse au titre de la garantie de parfait achèvement.")
        if method.fiche_entretien_applicable:
            reasons.append("Le défaut d'entretien par usure normale n'est pas retenu : à ce stade très précoce, l'usure d'un organe ou joint d'entretien n'est pas une cause raisonnable par défaut ; rechercher une origine constructive ou une défaillance initiale.")
    elif maintenance_kind == "chauffage_pac_gbf_forclos":
        decision_code = "REFUS_GARANTIE_PROPOSE"
        decision_label = "Non-garantie proposée - chauffage/PAC : garantie de bon fonctionnement forclose"
        sortie = "D1 - Non décennal probable / élément d'équipement chauffage hors biennale"
        reasons.append("Corps d'état identifié : chauffage / génie climatique, pompe à chaleur air/eau et circuit frigorifique.")
        reasons.append("Le dommage vise une fuite de fluide frigorigène au niveau d'un raccord rapide / liaison frigo ; il ne s'agit pas d'une infiltration d'eau ni d'un défaut d'étanchéité de toiture.")
        reasons.append("L'équipement relève de la garantie de bon fonctionnement de deux ans ; au vu des dates, ce délai est forclos, et l'impropriété de l'ouvrage dans son ensemble n'est pas objectivée.")
    elif characterized_maintenance_context:
        decision_code = "REFUS_GARANTIE_PROPOSE"
        if maintenance_kind == "douche_mastic":
            decision_label = "Non-garantie proposée - défaut d'entretien des joints de douche"
            sortie = "D1 - Non décennal probable / entretien des mastics dominant"
            reasons.append("Infiltrations localisées en périphérie du receveur : le maintien en bon état d'usage des mastics souples relève de l'entretien normal du logement")
            reasons.append("Conséquences limitées déclarées : légères boursouflures ponctuelles en pied de cloison, sans infiltration en local inférieur ni perte d'usage mentionnée")
        elif maintenance_kind == "roof_upstand":
            decision_label = "Non-garantie proposée - défaut d'entretien toiture-terrasse"
            sortie = "D1 - Non décennal probable / CE entretien dominante"
            reasons.append("La vérification du bon état des relevés d'étanchéité répond strictement de l'entretien dû par la copropriété")
            reasons.append("Le défaut d'entretien caractérisé neutralise l'orientation garantie, même si une infiltration est alléguée")
        elif maintenance_kind == "plomberie_piece_usure":
            decision_label = "Non-garantie proposée - défaut d'entretien plomberie / pièce d'usure"
            sortie = "D1 - Non décennal probable / entretien pièce d'usure dominant"
            reasons.append("La fuite localisée d'un organe de plomberie soumis à usure relève de l'entretien/remplacement courant si elle survient à partir de la 3e année et sans indice de défaut constructif")
            reasons.append("Le défaut d'entretien caractérisé neutralise l'orientation garantie, sous validation humaine")
        else:
            decision_label = "Non-garantie proposée - défaut d'entretien caractérisé"
            sortie = "D1 - Non décennal probable / CE entretien dominante"
            reasons.append("Défaut d'entretien caractérisé par croisement corps d'état / pathologie / fiche entretien / âge du sinistre")
    elif mold_condensation_context and not (active_leak or humidity_measured or facts.mentions_solidite or facts.mentions_safety or facts.mentions_impropriete):
        decision_code = "REFUS_GARANTIE_PROPOSE"
        decision_label = "Refus de garantie proposé - moisissures ponctuelles / entretien ventilation"
        sortie = "D1 - Non décennal probable"
        reasons.append("Moisissures ponctuelles localisées : absence d'atteinte à la solidité ou d'impropriété à destination objectivée ; orientation entretien / ventilation")
    elif safety_ceiling_context and (materiality or photos_exploitable):
        if amount_ttc is not None and amount_ttc < TM_TTC:
            decision_code = "GARANTIE_INF_TM_A_VALIDER"
            decision_label = "Garantie possible inférieure au TM - sécurité à valider"
            sortie = "D3/D4 - Risque sécurité objectivé, quantum sous TM à valider"
            reasons.append("Élément suspendu/faux plafond avec risque de chute : la gravité tient au risque sécurité, pas à une cause étrangère abstraite")
        else:
            decision_code = "ESCALADE_SENIOR"
            decision_label = "Escalade expert senior - sécurité plafond"
            sortie = "D5 - Risque sécurité à instruire"
            reasons.append("Risque de chute en plafond : chiffrage ou périmètre à sécuriser")
    elif non_garantie_context and not (facts.mentions_solidite or facts.mentions_impropriete or active_leak or facts.mentions_safety):
        decision_code = "REFUS_GARANTIE_PROPOSE"
        decision_label = "Refus de garantie proposé"
        sortie = "D1 - Non décennal probable"
        reasons.append("Contexte de non-conformité / réserve / travaux non terminés sans gravité décennale objectivée")
    elif water_context and (materiality or humidity_measured or active_leak):
        if amount_ttc is not None and amount_ttc < TM_TTC:
            decision_code = "GARANTIE_INF_TM_A_VALIDER"
            decision_label = "Garantie acquise inférieure au TM - à valider"
            sortie = "D4 - Décennalité probable, quantum sous TM"
            reasons.append("Désordre eau/humidité objectivé et montant inférieur au ticket modérateur")
        else:
            decision_code = "GARANTIE_POSSIBLE_COMPLEMENT"
            decision_label = "Garantie possible - complément / chiffrage nécessaire"
            sortie = "D3 - Décennalité possible"
            reasons.append("Désordre eau/humidité potentiellement impropre, mais quantum ou preuve incomplète")
    elif facts.mentions_solidite:
        decision_code = "ESCALADE_SENIOR"
        decision_label = "Escalade expert senior"
        sortie = "D5 - Dossier sensible"
        reasons.append("Mention de solidité ou structure : décision automatisée exclue")
    elif not materiality and not facts.has_photos:
        decision_code = "DOSSIER_INSUFFISANT"
        decision_label = "Dossier insuffisant - demander pièces"
        sortie = "D2 - Décennalité non caractérisée"
        reasons.append("Matérialité non objectivée à ce stade")
    else:
        decision_code = "PREQUALIFICATION_A_VALIDER"
        decision_label = "Préqualification à valider"
        sortie = "D2/D3 - Orientation non verrouillée"
        reasons.append("Les éléments disponibles permettent une orientation mais pas une position ferme")

    # V3.6.8 : le score garantie exprime la robustesse de l'avis proposé, pas la probabilité de garantie.
    # Si la non-garantie est fondée sur une pièce d'usure / entretien caractérisé en 3e année ou au-delà,
    # le score doit être élevé, même si l'orientation est défavorable à la garantie.
    if decision_code == "REFUS_GARANTIE_PROPOSE" and maintenance_kind == "plomberie_piece_usure":
        garantie_score = max(garantie_score, 90)
        quantum_score = max(quantum_score, 80 if amount_ttc is not None else 60)
        reasons.append("Synthèse : non-garantie robuste car le dommage déclaré vise une vanne / pièce d'usure déjà remplacée, en 3e année ou au-delà, sans impropriété ni dommage étendu objectivé.")
    if decision_code == "REFUS_GARANTIE_PROPOSE" and maintenance_kind == "chauffage_pac_gbf_forclos":
        garantie_score = max(garantie_score, 88)
        quantum_score = max(quantum_score, 90 if amount_ttc is not None else 65)
        reasons.append("Synthèse : non-garantie robuste car le dossier vise un équipement de chauffage/PAC, une fuite du circuit frigorifique, une garantie biennale forclose et aucune impropriété décennale objectivée.")
    if decision_code == "REFUS_GARANTIE_PROPOSE_LOGGIA":
        garantie_score = max(garantie_score, 82)
        quantum_score = max(quantum_score, 30 if amount_ttc is None else 70)
        reasons.append("Synthèse : non-garantie robuste car le dossier ne fait apparaître qu'une trace en loggia / extérieur privatif, sans entrée d'eau en logement ni impropriété à destination objectivée.")

    ce = _cause_etrangere_label(facts, mode_options, retrieved, raw_text)

    if garantie_score >= 80 and quantum_score >= 75:
        pr = "P3 - Forte"
    elif garantie_score >= 65:
        pr = "P2 - Correcte"
    elif garantie_score >= 45:
        pr = "P1 - Limitée"
    else:
        pr = "P0 - Très faible"

    if decision_code == "REFUS_GARANTIE_PROPOSE_LOGGIA" and garantie_score >= 80:
        validation = "Vérification humaine standard"
    elif decision_code == "REFUS_GARANTIE_PROPOSE" and maintenance_kind in {"plomberie_piece_usure", "chauffage_pac_gbf_forclos"} and garantie_score >= 80:
        validation = "Vérification humaine standard"
    elif decision_code == "GARANTIE_INF_TM_A_VALIDER" or red_flags or garantie_score < 80 or amount_estimated:
        validation = "Validation humaine obligatoire"
    elif decision_code == "REFUS_GARANTIE_PROPOSE" and garantie_score >= 80:
        validation = "Vérification humaine standard"
    else:
        validation = "Validation humaine obligatoire"
    if decision_code == "ESS_NECESSAIRE_TOITURE":
        validation = "ESS / expertise sur site recommandée"
    elif decision_code == "REFUS_GARANTIE_PROPOSE" and maintenance_kind:
        validation = "Vérification humaine standard"
    elif facts.mentions_solidite or senior_sensitive or len(red_flags) >= 4:
        validation = "Escalade expert senior recommandée"

    tm_ht = TM_TTC / (1 + vat)
    ecart = None if amount_ttc is None else TM_TTC - amount_ttc
    robust = int(round(0.65 * garantie_score + 0.35 * quantum_score))
    return DecisionResult(
        decision_code=decision_code,
        decision_label=decision_label,
        garantie_score=garantie_score,
        quantum_score=quantum_score,
        robustesse_globale=robust,
        niveau_validation=validation,
        sortie_decennalite=sortie,
        cause_etrangere=ce,
        force_probatoire=pr,
        tva_rate=vat,
        tm_ttc=TM_TTC,
        tm_ht=round(tm_ht, 2),
        montant_ttc=amount_ttc,
        ecart_tm=round(ecart, 2) if ecart is not None else None,
        red_flags=list(dict.fromkeys(red_flags)),
        complements=list(dict.fromkeys(complements)),
        reasons=reasons,
        pricing=pricing.to_dict(),
        montant_estime=amount_estimated,
    )
