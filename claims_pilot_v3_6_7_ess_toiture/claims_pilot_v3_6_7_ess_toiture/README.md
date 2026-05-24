# ClaimsPilot V3.6.7 - Qualification DO

Version de démonstration Streamlit + lancement local Windows.

## Lancement local Windows
Double-cliquer sur `LANCER_CLAIMSPILOT_WINDOWS.bat`, puis ouvrir `http://localhost:8501`.

## Déploiement Streamlit Cloud
Sélectionner impérativement `streamlit_app.py` comme fichier principal et Python 3.12.

La V3.6.7 supprime l'usage de `st.form` pour limiter les blocages Streamlit Cloud et ajoute un bouton **Nouvelle analyse / reset** destiné à remplacer le reboot de l'application.



## V3.6.7 - verrou usure normale / âge du sinistre

Cette version généralise le raisonnement : le défaut d'entretien par usure normale n'est invocable que si l'élément en cause est normalement soumis à usure, que le défaut est caractérisé, et que l'âge du sinistre rend raisonnable l'entretien/remplacement. Dans les deux premières années, l'application privilégie l'instruction d'une origine constructive ; en première année, elle demande la mise en demeure GPA restée infructueuse avant toute mobilisation DO.

## V3.6.7

Ajout de la règle d’âge pour les infiltrations en périphérie de receveur de douche : défaut d’entretien invocable à partir de la 3e année seulement, sauf preuve forte contraire ; pendant les deux premières années, rechercher d’abord le défaut constructif. En première année, la mobilisation DO suppose la mise en demeure GPA restée infructueuse.


## V3.6.7 - ESS toiture / cause étrangère non neutralisée

Cette version corrige le cas “fuite au plafond du dernier étage / toiture” : le moteur extrait le dommage déclaré réel, ne confond plus la localisation avec des circulations, et oriente vers une ESS ou une demande de pièces ciblées lorsque les ouvrages surmontants ne sont pas visualisés. La cause étrangère est alors notée CE-X non neutralisée, avec demande de contrat d’entretien, CR du mainteneur, photos de toiture/terrasse technique, relevés, solins, évacuations EP, traversées et équipements techniques.
