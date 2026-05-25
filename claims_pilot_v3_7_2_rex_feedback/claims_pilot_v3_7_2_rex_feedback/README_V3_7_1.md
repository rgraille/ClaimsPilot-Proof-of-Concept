# ClaimsPilot V3.7.1

Correctifs métier et techniques :

- OCR des PDF scannés activé lorsque les dépendances sont disponibles.
- Ajout d'un `packages.txt` pour Streamlit Cloud afin d'installer Tesseract OCR.
- Analyse contextualisée des images : les photos sont analysées après extraction du texte des pièces, afin d'utiliser le contexte déclaratif.
- Extraction renforcée des déclarations Lamy / syndic : police, propriétaire, locataire, lot, localisation, réception, apparition.
- Nouvelle règle générale : trace ponctuelle en plafond de séjour sous terrasse supérieure, sans venue d'eau active ni contrariété d'occupation objectivée -> non-garantie proposée.
- Chiffrage indicatif en non-garantie : nettoyage / retouche peinture ponctuelle = 50 € TTC.
- Les vues de façade et les traces sèches/apathiques alimentent la robustesse sans transformer automatiquement le dossier en décennal.

Cette version ne code pas un cas particulier : elle ajoute une règle de raisonnement généralisable sur la matérialité de l'infiltration et le seuil décennal.
