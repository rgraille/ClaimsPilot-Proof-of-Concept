from __future__ import annotations

import io
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class ImageFinding:
    source_file: str
    image_name: str
    status: str  # EXPLOITABLE / PARTIEL / PEU_EXPLOITABLE / BLANC
    confidence: int
    width: int
    height: int
    observations: List[str]
    tags: List[str]
    technical_note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _context_has(text: str, words: List[str]) -> bool:
    low = (text or "").lower()
    return any(w in low for w in words)


def _edge_ratio(img_gray) -> float:
    try:
        from PIL import ImageFilter
        edges = img_gray.filter(ImageFilter.FIND_EDGES)
        hist = edges.histogram()
        total = sum(hist) or 1
        strong = sum(hist[40:])
        return strong / total
    except Exception:
        return 0.0


def analyze_image_bytes(data: bytes, source_file: str, image_name: str, context_text: str = "") -> ImageFinding:
    """Analyse visuelle locale, volontairement prudente.

    Cette fonction ne prétend pas remplacer une vision experte. Elle sert à :
    - repérer si une photo est exploitable ;
    - extraire des indices visuels simples ;
    - relier ces indices au vocabulaire de la déclaration.
    """
    observations: List[str] = []
    tags: List[str] = []
    try:
        from PIL import Image, ImageStat
        img = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = img.size
        thumb = img.copy()
        thumb.thumbnail((640, 640))
        gray = thumb.convert("L")
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        std = float(stat.stddev[0])
        # histogram-based ratios
        hist = gray.histogram()
        total = sum(hist) or 1
        dark_ratio = sum(hist[:55]) / total
        light_ratio = sum(hist[230:]) / total
        edge_ratio = _edge_ratio(gray)

        if light_ratio > 0.93 and std < 12:
            return ImageFinding(source_file, image_name, "BLANC", 20, w, h, ["Image majoritairement blanche ou non exploitable."], ["image_peu_exploitable"], "Image non exploitable pour objectiver le dommage.")
        if mean < 45 or std < 8:
            status = "PEU_EXPLOITABLE"
            confidence = 35
            observations.append("Image sombre ou peu contrastée ; exploitation limitée.")
        elif edge_ratio > 0.05 or std > 30:
            status = "EXPLOITABLE"
            confidence = 75
            observations.append("Photo suffisamment contrastée pour une lecture visuelle de premier niveau.")
        else:
            status = "PARTIEL"
            confidence = 55
            observations.append("Photo exploitable partiellement ; le contraste ou le cadrage limite l'analyse.")

        if _context_has(context_text, ["suspension", "luminaire", "élément suspendu", "element suspendu", "menace de tomber", "tomber du plafond", "risque de chute", "se décroche", "se decroche"]):
            tags.extend(["luminaire_decoratif", "fixation_defaillante", "risque_chute"])
            if status in {"EXPLOITABLE", "PARTIEL"}:
                observations.append("Le contexte déclaratif vise un luminaire / une suspension décorative qui se décroche.")
                observations.append("La photo est compatible avec un luminaire suspendu et une dégradation localisée au droit d'un point de fixation.")
                observations.append("L'objet analysé est le luminaire et sa fixation ; le faux plafond est le support apparent, pas le désordre principal.")
                observations.append("Le risque de chute doit être traité comme un point de sécurité à vérifier rapidement, avec mesure conservatoire possible.")
        elif _context_has(context_text, ["humidité", "humidite", "infiltration", "moisissure", "moisissures", "fuite", "tache", "condensation"]):
            tags.extend(["eau_humidite", "trace_visuelle"])
            if _context_has(context_text, ["moisissure", "moisissures", "condensation"]):
                tags.extend(["moisissures_ponctuelles", "condensation_probable", "angle_pied_mur"] )
                observations.append("Le contexte déclaratif vise des traces de moisissures ; la photo montre des traces noirâtres ponctuelles et localisées en angle / pied de mur.")
                observations.append("Le faciès est compatible avec des moisissures de condensation ponctuelles ou un déficit local de renouvellement d'air, sous réserve de contrôle de la VMC et de l'usage.")
                observations.append("Aucun indice visuel net de venue d'eau active ou de dégradation généralisée du support n'est relevé par l'analyse automatique.")
            else:
                observations.append("Le contexte déclaratif vise une humidité ou une trace ; la photo doit être rapprochée des zones visibles sans conclure automatiquement à une infiltration.")
        elif _context_has(context_text, ["fissure", "fissuration", "lézarde", "lezarde"]):
            tags.extend(["fissuration"])
            observations.append("Le contexte déclaratif vise une fissuration ; prévoir une photo avec échelle ou mesure d'ouverture.")
        elif _context_has(context_text, ["décollement", "decollement", "décoll", "decol", "soulèvement", "soulevement"]):
            tags.extend(["decollement"])
            observations.append("Le contexte déclaratif vise un décollement ou soulèvement ; vérifier la surface concernée et le risque de chute ou d'extension.")

        if dark_ratio > 0.10 and light_ratio > 0.10 and edge_ratio > 0.04:
            tags.append("contraste_defaut_support")
            observations.append("Présence de zones contrastées sur fond clair, pouvant correspondre à une dégradation locale du support ou de la fixation.")

        tags = list(dict.fromkeys(tags))
        note = " ; ".join(observations)
        return ImageFinding(source_file, image_name, status, confidence, w, h, observations, tags, note)
    except Exception as exc:
        return ImageFinding(source_file, image_name, "PEU_EXPLOITABLE", 10, 0, 0, [f"Image non analysée : {exc}"], ["erreur_analyse_image"], "Analyse image impossible.")


def summarize_image_findings(findings: List[ImageFinding]) -> str:
    if not findings:
        return ""
    lines = ["=== ANALYSE VISUELLE AUTOMATIQUE ==="]
    for f in findings:
        lines.append(f"Image {f.image_name} ({f.source_file}) : {f.status}, confiance {f.confidence}/100, {f.width}x{f.height}px")
        for obs in f.observations:
            lines.append(f"- {obs}")
        if f.tags:
            lines.append("- Tags : " + ", ".join(f.tags))
    return "\n".join(lines)


def visual_supports_materiality(findings: List[ImageFinding]) -> bool:
    return any(f.status in {"EXPLOITABLE", "PARTIEL"} and any(t in f.tags for t in ["risque_chute", "fixation_defaillante", "luminaire_decoratif", "decollement", "eau_humidite", "moisissures_ponctuelles", "condensation_probable", "fissuration", "contraste_defaut_support"]) for f in findings)


def visual_has_safety_risk(findings: List[ImageFinding]) -> bool:
    return any("risque_chute" in f.tags for f in findings)
