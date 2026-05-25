from __future__ import annotations

from pathlib import Path


def is_reference_output_document(filename: str, text: str = "") -> bool:
    """Détecte les livrables finaux fournis comme références, à ne pas utiliser comme déclaration.

    ClaimsPilot qualification doit raisonner sur la déclaration et ses pièces, pas recopier
    le rapport/lettre/notification finalement établis. Les documents détectés ici restent
    listés comme reçus, mais leur contenu n'alimente pas le moteur de qualification.
    """
    name = Path(filename or "").name.lower()
    low = (text or "").lower()
    name_markers = [
        "rapport unique",
        "notification beneficiaire",
        "notification bénéficiaire",
        "lt acc",
        "lettre accompagnement",
        "lettre confidentielle",
    ]
    text_markers = [
        "rapport preliminaire et d'expertise dommages ouvrage",
        "rapport préliminaire et d’expertise dommages ouvrage",
        "rapport préliminaire et d'expertise dommages ouvrage",
        "le présent courrier vaut notification de l’assureur",
        "le present courrier vaut notification de l'assureur",
        "je vous prie de trouver ci-joint mon rapport préliminaire",
        "je vous prie de trouver ci-joint mon rapport preliminaire",
    ]
    return any(m in name for m in name_markers) or any(m in low for m in text_markers)
