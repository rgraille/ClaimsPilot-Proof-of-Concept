from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from .extractor import ExtractedFacts
from .retrieval import RetrievedSource
from .decision import DecisionResult
from .evidence import EvidenceAssessment
from .expertal import ExpertalAnalysis


def _fmt_money(v):
    if v is None:
        return "Non renseigné"
    return f"{v:,.2f} €".replace(",", " ")


def generate_agent_pack(
    facts: ExtractedFacts,
    retrieved: List[RetrievedSource],
    decision: DecisionResult,
    raw_text: str = "",
    evidence: EvidenceAssessment | None = None,
    expertal: Optional[ExpertalAnalysis] = None,
) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = []
    lines.append("# Pack agent ClaimsPilot - réponse générée")
    lines.append("")
    lines.append(f"Date de génération : {now}")
    lines.append("")
    lines.append("## 1. Synthèse de la déclaration")
    lines.append(f"- Dommage déclaré : {facts.declared_damage or 'Non extrait'}")
    if expertal:
        lines.append(f"- Dommage analysé : {expertal.analysed_damage}")
        lines.append(f"- Position dans la décennale : {expertal.decade_year}")
    lines.append(f"- Opération : {facts.operation or 'Non renseignée'}")
    lines.append(f"- Type d'ouvrage : {facts.construction_type}")
    lines.append(f"- Localisation probable : {facts.location}")
    lines.append(f"- Réception : {facts.reception_date or 'Non renseignée'}")
    lines.append(f"- Date sinistre / déclaration : {facts.loss_date or facts.declaration_date or 'Non renseignée'}")
    lines.append("")

    if expertal:
        lines.append("## 2. Démarche expertale structurée")
        lines.append("Cette section suit la logique métier : dommage déclaré → temps décennal → type d'ouvrage → lieu → constats/photos → pathologie → élément affecté → gravité → cause étrangère → garantie → réparation.")
        lines.append("")
        for step in expertal.reasoning_path:
            lines.append(f"- {step}")
        lines.append("")
        lines.append("### Lecture métier synthétique")
        lines.append(f"- Élément affecté : **{expertal.affected_element_category}** — {expertal.affected_element_detail}")
        lines.append(f"- Contexte ouvrage : {expertal.construction_context}")
        lines.append(f"- Contexte local / zone : {expertal.location_context}")
        lines.append(f"- Lecture des photos : {expertal.visual_context}")
        lines.append(f"- Gravité : {expertal.severity_assessment}")
        lines.append(f"- Cause étrangère : {expertal.cause_etrangere_screening}")
        lines.append(f"- Garantie : {expertal.guarantee_analysis}")
        lines.append(f"- Réparation : {expertal.repair_principle}")
        lines.append("")
        lines.append("### Signes/pathologies retenus")
        for s in expertal.pathology_signs:
            lines.append(f"- {s}")
        lines.append("")
        lines.append("### Causes techniques possibles")
        for c in expertal.likely_causes:
            lines.append(f"- {c}")
        lines.append("")
        lines.append("### Marqueurs de solidité / impropriété")
        for m in expertal.impropriete_markers:
            lines.append(f"- {m}")
        lines.append("")

    lines.append("## 3. Éléments reçus et éléments à obtenir")
    if evidence:
        lines.append("### Éléments reçus / extraits")
        if evidence.received:
            for item in evidence.received:
                lines.append(f"- {item}")
        else:
            lines.append("- Aucun élément probant reçu automatiquement.")
        lines.append("")
        lines.append("### Éléments à vérifier")
        if evidence.to_verify:
            for item in evidence.to_verify:
                lines.append(f"- {item}")
        else:
            lines.append("- Aucun point de vérification spécifique détecté.")
        lines.append("")
        lines.append("### Éléments manquants")
        missing = list(evidence.missing)
        if expertal:
            missing.extend(expertal.elements_to_obtain)
        missing = list(dict.fromkeys(missing))
        if missing:
            for item in missing:
                lines.append(f"- {item}")
        else:
            lines.append("- Aucun élément bloquant manquant détecté.")
        lines.append("")

    lines.append("## 4. Sources métier croisées")
    if retrieved:
        for r in retrieved:
            c = r.card
            lines.append(f"### {c.famille} — score {r.score}")
            lines.append(f"Source : {c.source}")
            lines.append(f"Mots-clés reconnus : {', '.join(r.matched_keywords[:12]) or '—'}")
            lines.append(f"Lecture métier : {c.source_detail}")
            lines.append("Signes à rechercher : " + "; ".join(c.signes[:5]))
            lines.append("Causes possibles : " + "; ".join(c.causes_possibles[:5]))
            lines.append("Points à vérifier : " + "; ".join(c.points_a_verifier[:6]))
            lines.append("")
    else:
        lines.append("Aucune fiche métier fortement corrélée n'a été retrouvée. Compléter la description du dommage.")

    lines.append("## 5. Analyse technique générée")
    if expertal:
        lines.append(expertal.guarantee_analysis)
        lines.append("")
        lines.append(expertal.repair_principle)
    else:
        lines.append(_technical_analysis(facts, retrieved, decision))
    lines.append("")
    lines.append("## 6. Avis sur les garanties - proposition")
    lines.append(f"- Décision proposée : **{decision.decision_label}**")
    lines.append(f"- Sortie décennalité : {decision.sortie_decennalite}")
    lines.append(f"- Cause étrangère : {decision.cause_etrangere}")
    lines.append(f"- Force probatoire : {decision.force_probatoire}")
    lines.append(f"- Niveau de contrôle : **{decision.niveau_validation}**")
    lines.append("")
    lines.append(_guarantee_wording(facts, retrieved, decision))
    lines.append("")
    lines.append("## 7. Chiffrage / TM")
    lines.append(f"- Montant TTC retenu : {_fmt_money(decision.montant_ttc)}")
    if decision.montant_estime:
        lines.append("- Nature du montant : **pré-chiffrage estimatif**, à valider humainement")
    else:
        lines.append("- Nature du montant : montant extrait du dossier ou non renseigné")
    if decision.pricing:
        lines.append(f"- Méthode : {decision.pricing.get('method', '—')}")
        lines.append(f"- Détail : {decision.pricing.get('details', '—')}")
    lines.append(f"- Ticket modérateur : {_fmt_money(decision.tm_ttc)} TTC")
    lines.append(f"- TVA retenue : {int(decision.tva_rate * 100)} %")
    lines.append(f"- Équivalent TM HT : {_fmt_money(decision.tm_ht)}")
    if decision.ecart_tm is not None:
        lines.append(f"- Écart au TM : {_fmt_money(decision.ecart_tm)}")
    lines.append("")
    lines.append("## 8. Robustesse et alertes")
    lines.append(f"- Robustesse garantie : {decision.garantie_score}/100")
    lines.append(f"- Robustesse quantum : {decision.quantum_score}/100")
    lines.append(f"- Robustesse globale : {decision.robustesse_globale}/100")
    if decision.red_flags:
        lines.append("- Alertes : " + "; ".join(decision.red_flags))
    else:
        lines.append("- Alertes : aucune alerte majeure détectée")
    if decision.complements:
        lines.append("- Compléments à demander : " + "; ".join(decision.complements))
    else:
        lines.append("- Compléments à demander : aucun complément bloquant détecté")
    lines.append("")
    lines.append("## 9. Traçabilité moteur")
    for reason in decision.reasons:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## 10. Sorties JSON")
    lines.append("```json")
    lines.append(json.dumps({
        "facts": facts.to_dict(),
        "expertal": expertal.to_dict() if expertal else None,
        "evidence": evidence.to_dict() if evidence else None,
        "sources": [r.to_dict() for r in retrieved],
        "decision": decision.to_dict(),
    }, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


def _technical_analysis(facts: ExtractedFacts, retrieved: List[RetrievedSource], decision: DecisionResult) -> str:
    parts = []
    if facts.mentions_ceiling_suspension:
        parts.append("La déclaration vise un élément suspendu ou une suspension décorative en plafond. Les photos doivent être lues en priorité sous l'angle de la fixation, du support et du risque de chute. La gravité ne se raisonne pas comme une simple finition : le marqueur principal est la sécurité des personnes en zone accessible.")
    if facts.mentions_humidity_or_water:
        parts.append("La déclaration évoque un phénomène d'eau, d'humidité, de moisissure ou de fuite. Ce type de dommage nécessite d'abord d'objectiver la matérialité : humidité active, test d'arrosage, recherche de fuite ou constat visuel exploitable.")
    if facts.mentions_crack:
        parts.append("La déclaration évoque une fissuration. Il faut distinguer la fissure esthétique de la fissure active, infiltrante ou structurelle, en documentant largeur, évolution, localisation et conséquences.")
    if facts.mentions_detachment and not facts.mentions_ceiling_suspension:
        parts.append("La déclaration évoque un décollement ou un soulèvement. L'analyse doit rechercher si le désordre affecte seulement l'aspect ou s'il crée un risque de chute, une perte d'usage ou une généralisation.")
    if facts.mentions_reserve_or_gpa:
        parts.append("La déclaration comporte des indices de réserve, GPA, travaux non terminés ou non-conformité. Ce point peut orienter hors garantie DO obligatoire si aucune gravité décennale n'est objectivée.")
    if retrieved:
        families = ", ".join(r.card.famille for r in retrieved[:3])
        parts.append(f"Les fiches les plus pertinentes pour le croisement documentaire sont : {families}.")
    if "Aucune cause étrangère" in decision.cause_etrangere:
        parts.append("Aucune cause étrangère concrète n'est identifiée dans les éléments reçus. L'application ne doit donc pas invoquer l'entretien, l'usage, l'usure ou un tiers de manière abstraite.")
    if not parts:
        parts.append("Les éléments déclaratifs ne permettent pas encore de rattacher le dommage à une famille pathologique précise. Il faut enrichir la déclaration par photos, localisation et description des symptômes observables.")
    return "\n\n".join(parts)


def _guarantee_wording(facts: ExtractedFacts, retrieved: List[RetrievedSource], decision: DecisionResult) -> str:
    if facts.mentions_ceiling_suspension and decision.decision_code == "GARANTIE_INF_TM_A_VALIDER":
        return (
            "Les éléments reçus décrivent une suspension ou un élément en faux plafond menaçant de tomber, avec photos exploitables. "
            "La position proposée est une garantie possible inférieure au TM, à valider par un humain, car la gravité peut tenir au risque de chute et à la sécurité des personnes. "
            "Aucune cause étrangère ne doit être invoquée à ce stade faute d'indice concret d'entretien, d'usage, d'usure ou d'intervention tierce."
        )
    if decision.decision_code == "REFUS_GARANTIE_PROPOSE":
        return (
            "Au vu des éléments disponibles, le dommage paraît relever d'une non-conformité, d'une réserve, d'une GPA, "
            "de travaux non terminés ou d'un défaut dépourvu de gravité décennale objectivée. En l'état, il n'est pas démontré "
            "qu'il compromette la solidité de l'ouvrage ou le rende impropre à sa destination. La garantie obligatoire DO peut donc "
            "être proposée comme non mobilisable, sous réserve de validation humaine."
        )
    if decision.decision_code == "GARANTIE_INF_TM_A_VALIDER":
        return (
            "Le dommage présente des indices compatibles avec une impropriété à destination ou une atteinte fonctionnelle, et un montant "
            "inférieur au ticket modérateur a été identifié ou estimé. La proposition est donc une garantie acquise ou possible inférieure au TM, "
            "mais elle doit être vérifiée humainement, notamment sur le risque sériel, la pérennité de la réparation et la fiabilité du quantum."
        )
    if decision.decision_code == "ESCALADE_SENIOR":
        return "La présence d'indices relatifs à la solidité, la structure ou la sécurité impose une analyse d'expert senior avant toute position de garantie."
    if decision.decision_code == "DOSSIER_INSUFFISANT":
        return "La matérialité du dommage n'est pas suffisamment objectivée. La position doit rester en attente de pièces ou investigations complémentaires."
    return "La position de garantie n'est pas verrouillée. L'application propose une orientation technique et les compléments nécessaires avant validation."
