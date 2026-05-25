from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any


@dataclass(frozen=True)
class SourceCard:
    id: str
    famille: str
    source: str
    source_detail: str
    keywords: List[str]
    signes: List[str]
    causes_possibles: List[str]
    points_a_verifier: List[str]
    logique_garantie: str
    mode_reparatoire_type: List[str]
    red_flags: List[str]
    carbon_aliases: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SOURCE_CARDS: List[SourceCard] = [

    SourceCard(
        id="PAC_CHAUFFAGE_FRIGORIFIQUE",
        famille="Chauffage / pompe à chaleur / circuit frigorifique",
        source="Fiches équipements.pdf + doctrine ClaimsPilot",
        source_detail="PAC air/eau, chauffage, eau chaude sanitaire, liaison frigorifique, fluide R32, raccord rapide, dépannage et garantie de bon fonctionnement.",
        keywords=["pompe à chaleur", "pompe a chaleur", "pac", "chauffage", "eau chaude sanitaire", "plancher chauffant", "radiateur", "fluide frigorigène", "fluide frigorigene", "circuit frigo", "liaison frigo", "raccord rapide", "r32", "réseau cuivre", "reseau cuivre", "module extérieur", "module exterieur", "résistance électrique", "resistance electrique"],
        signes=["fuite de fluide frigorigène", "défaut de raccord rapide", "perte de charge frigorifique", "mode secours électrique", "chauffage dégradé", "ECS dégradée", "devis de recharge et reprise liaison frigo"],
        causes_possibles=["fuite sur raccord frigorifique", "défaut de raccordement", "défaut d'étanchéité du circuit frigorifique", "maintenance ou dépannage PAC", "défaillance d'un équipement dissociable"],
        points_a_verifier=["date de réception et délai biennal", "rapport du mainteneur", "localisation du raccord fuyard", "fonctionnement chauffage/ECS ou secours", "devis de réparation", "preuve d'impropriété globale éventuelle"],
        logique_garantie="Un désordre affectant une PAC ou sa liaison frigorifique relève d'abord de l'équipement de chauffage et de la garantie de bon fonctionnement de deux ans. Au-delà de ce délai, la DO obligatoire n'est pas mobilisable sauf impropriété de l'ouvrage dans son ensemble ou atteinte à la solidité objectivée.",
        mode_reparatoire_type=["recherche et réparation de fuite frigorifique", "récupération fluide", "mise sous azote", "tirage au vide", "brasure ou remplacement liaison frigo", "recharge R32", "contrôle d'étanchéité", "remise en service PAC"],
        red_flags=["période hivernale", "absence totale chauffage/ECS", "enfants ou occupants vulnérables", "mesure conservatoire", "fluide frigorigène"],
        carbon_aliases=["cuivre", "fluide frigorigène", "transport", "brasure"],
    ),
    SourceCard(
        id="SUSPENSION_FAUX_PLAFOND_SECURITE",
        famille="Faux plafond / suspension décorative / risque de chute",
        source="Fiches aménagements.pdf + Référentiel opérationnel complet.docx",
        source_detail="AQC : désordres d'aménagements intérieurs et décollements au plafond ; doctrine interne : les non-façons générant un risque santé/sécurité peuvent faire monter la gravité si le risque est objectivé par photos/constat.",
        keywords=["faux plafond", "plafond", "suspension", "luminaire", "élément suspendu", "element suspendu", "menace de tomber", "tomber", "chute", "sécurité", "securite", "mise en sécurité", "mise en securite", "décrocher", "decrocher", "arrachement"],
        signes=["élément suspendu qui menace de tomber", "dégradation localisée au droit d'une fixation", "arrachement visible du support", "risque de chute dans une zone accessible", "mise en sécurité demandée"],
        causes_possibles=["défaut de fixation ou de supportage", "support inadapté ou dégradé", "arrachement ponctuel", "défaut d'exécution de l'élément décoratif", "intervention tierce uniquement si elle est documentée"],
        points_a_verifier=["zone accessible au public ou aux occupants", "poids et dimensions de l'élément", "mode de fixation", "support réel derrière le faux plafond", "existence d'autres suspensions identiques", "mesure conservatoire immédiate"],
        logique_garantie="Ne pas invoquer de cause étrangère si aucune fiche entretien applicable et aucun élément concret d'entretien/usage/tiers n'est présent. La question principale est le risque actuel de chute et son rattachement à un élément d'ouvrage ou d'équipement incorporé.",
        mode_reparatoire_type=["mise en sécurité", "dépose de la suspension", "reprise de fixation/support", "rebouchage et reprise ponctuelle plafond", "repose ou remplacement localisé"],
        red_flags=["risque de chute", "parties communes", "sécurité des personnes", "possibilité de série sur suspensions identiques"],
        carbon_aliases=["plaque platre", "enduit", "peinture", "acier", "fixation"],
    ),
    SourceCard(
        id="DOUCHE_ZERO_RESSAUT",
        famille="Salle d'eau / douche / infiltration",
        source="Fiches douches zéro ressaut.pdf + Fiches entretien.pdf",
        source_detail="Fiche pratique UNECP-FFB FP9 + logique entretien : étanchéité en salle d'eau, receveur, joints périphériques, mastics souples soumis au maintien en bon état d'usage.",
        keywords=["douche", "italienne", "zero ressaut", "salle de bain", "salle d'eau", "bac", "receveur", "pare douche", "siphon", "caniveau", "humidite", "moisissure", "infiltration", "joint", "mastic", "silicone", "périphérie", "peripherie", "pied de cloison", "boursouflure", "mitigeur", "rosette", "faience"],
        signes=["tache d'humidité", "moisissures", "humidité active", "dégradation d'enduit ou peinture en pied de cloison", "écoulement lors d'arrosages ou utilisation de la douche"],
        causes_possibles=["défaut d'entretien des mastics souples périphériques du receveur", "défaut d'étanchéité périphérique du receveur", "défaut de joint au droit du pare-douche", "absence ou défaut de traitement étanche aux traversées EF/ECS", "défaut de pente ou évacuation", "absence/inadaptation de SPEC ou SEL"],
        points_a_verifier=["localisation exacte de la trace par rapport au receveur et aux traversées", "état visuel des mastics souples périphériques", "test humidimètre", "arrosage sélectif du pare-douche, du mitigeur et du joint périphérique", "existence d'une intervention antérieure", "étendue des conséquences dans les pièces voisines ou locaux inférieurs"],
        logique_garantie="Une infiltration active en salle d'eau peut caractériser une impropriété à destination si l'usage normal de la douche ou de la pièce humide est affecté. En revanche, une infiltration localisée en périphérie du receveur, en milieu de décennale et avec conséquences ponctuelles, doit conduire à discuter prioritairement le maintien en bon état d'usage des mastics souples, donc l'entretien.",
        mode_reparatoire_type=["dépose ponctuelle des joints défaillants", "traitement étanche des traversées", "reprise du joint périphérique receveur / pare-douche", "reprise des supports dégradés", "remise en peinture ou faïence localisée"],
        red_flags=["récurrence", "ancienne intervention inefficace", "humidité active", "plusieurs logements", "risque sériel douche", "absence de test d'arrosage", "défaut d'entretien des mastics"],
        carbon_aliases=["joint silicone", "peinture", "reprise enduit", "carrelage mural", "étanchéité"],
    ),
    SourceCard(
        id="CARRELAGE_SOL",
        famille="Carrelage / revêtements de sol",
        source="e-sols-carreles-vigilance.pdf + Fiches aménagements.pdf",
        source_detail="AQC : fissuration, décollement, soulèvement, joints périphériques/fractionnement, support, délai de séchage, collage/scellement.",
        keywords=["carrelage", "carreau", "carreaux", "fissure", "fissuration", "decollement", "décollement", "soulevement", "soulèvement", "descellement", "chape", "joint de fractionnement", "plancher chauffant", "sol"],
        signes=["carreaux fissurés", "carreaux décollés", "soulèvement brutal", "son creux", "fissures en continuité avec le support", "désaffleurement"],
        causes_possibles=["retrait excessif de la chape", "absence de joints périphériques ou de fractionnement", "préparation insuffisante du support", "collage inadapté", "mise en service trop rapide", "support ou isolant compressible"],
        points_a_verifier=["localisation des fissures", "continuité avec support", "sondage au maillet", "présence de joints périphériques et fractionnement", "nature du support", "âge de la chape et mise en service"],
        logique_garantie="La garantie dépend de la gravité : un désordre esthétique isolé est souvent insuffisant, mais un soulèvement dangereux, une impropriété d'usage ou une généralisation peut justifier une analyse décennale renforcée.",
        mode_reparatoire_type=["dépose-repose localisée", "reprise chape/support", "création ou reprise des joints", "repose carrelage", "reprise plinthes"],
        red_flags=["grand format", "plancher chauffant", "désordre généralisé", "risque de chute", "locaux recevant du public"],
        carbon_aliases=["carrelage", "colle carrelage", "chape", "mortier", "plinthe"],
    ),
    SourceCard(
        id="FAIENCE_MURALE_SECURITE",
        famille="Faïence / revêtement mural en local humide / risque de chute",
        source="Fiches aménagements.pdf + e-sols-carreles-vigilance.pdf + démarche expertale R. Graille",
        source_detail="Analyse des revêtements collés/scellés : sillons de colle intacts, absence d'adhérence, son creux, décollement généralisé et risque de chute en salle de bain.",
        keywords=["faience", "faïence", "carreaux muraux", "carreau mural", "revêtement mural", "revetement mural", "sonne creux", "sillons de colle", "salle de bain", "décollement", "decollement", "chute", "tomber"],
        signes=["carreaux muraux décollés", "son creux", "sillons de colle intacts", "absence d'adhérence", "risque de chute de carreaux", "désordre en salle de bains"],
        causes_possibles=["défaut d'application de la colle", "support mal préparé", "colle inadaptée au support ou au local humide", "absence de transfert de colle", "défaut généralisé d'adhérence"],
        points_a_verifier=["zones qui sonnent creux", "surface de murs concernée", "risque de chute immédiat", "état des joints", "présence de SPEC en local humide", "photos larges et rapprochées"],
        logique_garantie="Un revêtement mural est un équipement inerte ; il peut néanmoins relever de l'impropriété si le risque de chute pour les occupants est objectivé ou si la salle d'eau ne peut plus être utilisée normalement.",
        mode_reparatoire_type=["sondage des zones creuses", "dépose des carreaux non adhérents", "préparation du support", "repose faïence", "reprise joints et étanchéité locale"],
        red_flags=["risque de chute", "salle d'eau", "défaut généralisé", "absence de surface chiffrée"],
        carbon_aliases=["carrelage mural", "colle carrelage", "joint", "enduit", "peinture"],
    ),
    SourceCard(
        id="VMC_CONDENSATION",
        famille="Ventilation / condensation / moisissures",
        source="Fiches équipements.pdf + Fiches entretien.pdf",
        source_detail="AQC : VMC simple/double flux, dimensionnement, accès entretien, encrassement, gaines, points bas, condensation et moisissures.",
        keywords=["vmc", "ventilation", "condensation", "moisissure", "moisissures", "air", "bouche", "extraction", "entree d'air", "entrée d'air", "gaine", "debit", "débit", "humidite", "humidité"],
        signes=["moisissures ponctuelles en angle ou pied de mur", "condensation", "déficit de renouvellement d'air", "absence ou faiblesse de débit", "bouches encrassées", "gaines écrasées ou avec point bas", "bruit ou sifflement"],
        causes_possibles=["déficit de ventilation ou de renouvellement d'air", "défaut de conception ou dimensionnement", "mauvais équilibrage", "gaines écrasées ou non calorifugées", "entretien insuffisant des bouches ou du groupe", "obturation des entrées d'air par l'occupant"],
        points_a_verifier=["mesure des débits", "état des bouches", "fonctionnement permanent du groupe", "détalonnage des portes", "usage des locaux", "entretien périodique"],
        logique_garantie="La présence de moisissures ponctuelles ne suffit pas à caractériser une impropriété à destination. En l'absence d'humidité active, d'infiltration objectivée, de généralisation ou de risque santé caractérisé, l'orientation est non décennale ; le traitement relève d'abord du nettoyage et de l'entretien/réglage des installations de ventilation.",
        mode_reparatoire_type=["nettoyage des traces à l'eau légèrement javellisée", "nettoyage ou remplacement des bouches", "contrôle des débits VMC", "réglage/équilibrage", "reprise gaines si défaut constructif objectivé", "reprise ponctuelle de peinture seulement si nécessaire"],
        red_flags=["absence d'entretien", "obturation entrées d'air", "pathologie généralisée", "risque santé", "logement très occupé"],
        carbon_aliases=["peinture", "gaine ventilation", "bouche extraction", "groupe vmc"],
    ),
    SourceCard(
        id="FACADE_INFILTRATION",
        famille="Façade / enveloppe / infiltration",
        source="Fiches enveloppe.pdf + Fiches gros-oeuvre.pdf",
        source_detail="AQC : défauts d'étanchéité des façades, briques apparentes, enduits, points singuliers, appuis, rejets d'eau, fissuration.",
        keywords=["facade", "façade", "enduit", "ravalement", "brique", "mur", "appui", "fenetre", "fenêtre", "tableau", "infiltration", "ruissellement", "fissure", "cloque", "decollement", "décollement"],
        signes=["infiltration en façade", "fissuration d'enduit", "cloquage", "décollement de revêtement", "humidité intérieure au droit d'une baie", "efflorescences"],
        causes_possibles=["mauvaise conception des points singuliers", "absence de rejet d'eau", "défaut de joints", "revêtement inadapté au support", "fissuration support", "défaut de perméance"],
        points_a_verifier=["exposition pluie/vent", "présence de fissures actives", "traitement des appuis et tableaux", "continuité des joints", "compatibilité revêtement/support", "ancienneté et entretien"],
        logique_garantie="L'infiltration objectivée peut relever de l'impropriété à destination si elle affecte l'habitabilité ou l'usage. Une simple fissure esthétique ou un défaut de finition sans infiltration active reste insuffisant.",
        mode_reparatoire_type=["traitement fissures", "reprise joints", "reprise appui/tableau", "revêtement d'imperméabilité localisé", "réfection enduit"],
        red_flags=["infiltrations multiples", "façade exposée", "désordre généralisé", "ravalement récent", "ancien bâti"],
        carbon_aliases=["enduit facade", "peinture facade", "mortier", "mastic", "bavette"],
    ),
    SourceCard(
        id="ETANCHEITE_TOITURE_TERRASSE_BALCON",
        famille="Étanchéité / toiture-terrasse / balcon",
        source="Fiches enveloppe.pdf + Fiches entretien.pdf + Barème CRAC",
        source_detail="Pathologies d'étanchéité : relevés, évacuations, joints, protection, entretien, infiltrations, mise en charge d'eau.",
        keywords=["toiture terrasse", "terrasse", "balcon", "loggia", "releve", "relevé", "etancheite", "étanchéité", "gouttiere", "évacuation", "ep", "eaux pluviales", "infiltration", "plafond", "acrotère"],
        signes=["infiltration sous terrasse", "décollement de relevé", "stagnation d'eau", "mise en charge", "traces au plafond", "dégradation nez de dalle"],
        causes_possibles=["défaut de relevé", "défaut de protection", "évacuation obstruée", "pente insuffisante", "joint défaillant", "défaut d'entretien"],
        points_a_verifier=["âge du désordre dans la décennale", "entretien des EP", "test d'arrosage ou mise en eau", "état des relevés", "présence d'obstruction", "zone affectée en dessous"],
        logique_garantie="Une infiltration active par étanchéité peut relever de la garantie obligatoire. En revanche, un défaut d'entretien ou l'obstruction des évacuations peut constituer une cause étrangère ou une exclusion selon dossier.",
        mode_reparatoire_type=["reprise relevé", "reprise joint", "curage évacuation", "réfection étanchéité localisée", "reprise plafond/peinture"],
        red_flags=["défaut d'entretien", "mise en charge", "risque sécurité balcon", "infiltration logement", "plusieurs lots"],
        carbon_aliases=["membrane étanchéité", "mastic", "peinture", "reprise béton"],
    ),
    SourceCard(
        id="GROS_OEUVRE_STRUCTURE",
        famille="Structure / gros œuvre / fissuration",
        source="Fiches gros-oeuvre.pdf + Baromètre sinistralité gros œuvre 2024",
        source_detail="AQC/SMA : fondations, murs, façades lourdes, dallages, planchers, fissures, stabilité, infiltrations par fissuration.",
        keywords=["fissure", "lézarde", "lezarde", "affaissement", "tassement", "fondation", "dallage", "plancher", "beton", "béton", "armature", "corrosion", "structure", "solidite", "solidité"],
        signes=["fissures évolutives", "fissures traversantes", "désaffleurement", "affaissement", "déformation", "éclatement béton", "corrosion armatures"],
        causes_possibles=["mouvement de structure", "retrait", "fondations inadaptées", "défaut de ferraillage", "corrosion", "défaut de mise en œuvre béton", "sol argileux ou hétérogène"],
        points_a_verifier=["largeur et évolution des fissures", "localisation structurale", "présence d'infiltration", "étude de sol", "déformation associée", "atteinte à la stabilité"],
        logique_garantie="L'atteinte à la solidité ou le risque structurel impose une escalade expert senior. Une fissure isolée non évolutive et sans conséquence d'usage peut rester non décennale ou insuffisamment caractérisée.",
        mode_reparatoire_type=["diagnostic structure", "injection ou agrafage", "reprise béton", "traitement corrosion", "renforcement local"],
        red_flags=["solidité", "évolution", "sécurité", "fondations", "plusieurs logements", "coût potentiellement élevé"],
        carbon_aliases=["béton", "acier", "mortier", "résine injection"],
    ),
    SourceCard(
        id="PLOMBERIE_RESEAUX",
        famille="Plomberie / réseaux / fuite",
        source="Fiches équipements.pdf + Fiches douches zéro ressaut.pdf",
        source_detail="Réseaux EF/ECS, traversées, raccords, fuites, dégâts d'eau, alimentations, évacuations.",
        keywords=["fuite", "plomberie", "canalisation", "reseau", "réseau", "ef", "ecs", "alimentation", "evacuation", "évacuation", "raccord", "siphon", "mitigeur", "robinet", "colonne"],
        signes=["fuite visible", "humidité active", "baisse de pression", "trace au droit d'un réseau", "écoulement reproduit", "dégât des eaux"],
        causes_possibles=["raccord défectueux", "défaut de traversée", "défaut de sertissage", "fuite évacuation", "joint défaillant", "intervention tierce"],
        points_a_verifier=["localisation exacte du réseau", "test en charge", "origine EF/ECS ou évacuation", "accessibilité", "intervention antérieure", "étendue des conséquences"],
        logique_garantie="Une fuite encastrée ou affectant un équipement indissociable peut caractériser l'impropriété si elle empêche l'usage normal ou dégrade l'ouvrage ; une fuite sur élément accessible/remplaçable peut nécessiter une analyse GBF ou facultative.",
        mode_reparatoire_type=["reprise raccord", "remplacement tronçon", "traitement traversée", "reprise support", "remise en état finitions"],
        red_flags=["fuite active", "réseau encastré", "conséquences multiples", "recherche de fuite nécessaire", "intervention tierce"],
        carbon_aliases=["tube cuivre", "tube multicouche", "raccord", "peinture", "plaque platre"],
    ),
    SourceCard(
        id="NON_CONFORMITE_RESSAUT_RESERVE",
        famille="Non-conformité / travaux non terminés / ressaut",
        source="Clausier sur la délégation V2017.pdf + exemple rapport Villa Murat",
        source_detail="Cas où le désordre relève davantage d'une non-conformité, réserve, GPA, intervention spontanée ou travaux non terminés que d'un dommage décennal.",
        keywords=["ressaut", "non conformite", "non-conformité", "reserve", "réserve", "travaux non termines", "travaux non terminés", "gpa", "parfait achevement", "achèvement", "intervention spontanee", "intervention spontanée", "terminer", "finir"],
        signes=["élément non conforme", "hauteur non conforme", "défaut apparent", "travaux repris par une entreprise", "engagement d'intervention"],
        causes_possibles=["travaux non achevés", "non-conformité contractuelle ou réglementaire", "défaut de finition", "réserve ou GPA", "intervention postérieure par tiers"],
        points_a_verifier=["réserve à réception", "date d'apparition", "année dans la décennale", "existence d'un engagement de reprise", "gravité réelle solidité/destination", "sécurité objectivée ou seulement alléguée"],
        logique_garantie="Une non-conformité ou un défaut de travaux non terminés ne suffit pas à mobiliser la DO si la solidité et la destination ne sont pas compromises. Le dossier peut toutefois être sensible si un risque sécurité réel est objectivé.",
        mode_reparatoire_type=["reprise élément non conforme", "intervention entreprise", "mise en conformité", "pas d'indemnité si intervention spontanée"],
        red_flags=["sécurité", "réglementation incendie", "parties communes", "copropriété", "risque contestation"],
        carbon_aliases=["mortier", "acier", "béton"],
    ),
]


def get_source_cards() -> List[SourceCard]:
    return list(SOURCE_CARDS)
