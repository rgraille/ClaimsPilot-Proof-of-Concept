# ClaimsPilot V3.6.9

## Corrections principales

- Recentrage du moteur sur les dossiers chauffage / pompe à chaleur / circuit frigorifique.
- Identification du corps d'état : chauffage / génie climatique.
- Distinction entre fuite de fluide frigorigène et infiltration d'eau : une fuite R32 / circuit frigo ne doit plus déclencher les branches toiture, étanchéité, eau-humidité ou plomberie sanitaire.
- Qualification de l'élément affecté : PAC air/eau, liaison frigorifique, raccord rapide, réseau cuivre, fluide R32.
- Orientation garantie : non-garantie proposée lorsque la garantie de bon fonctionnement de 2 ans est forclose et que l'impropriété de l'ouvrage dans son ensemble n'est pas objectivée.
- Actions correctives proposées : réparation fuite frigorifique, mise sous azote, tirage au vide, recharge R32, contrôle d'étanchéité, remise en service.
- Chiffrage : extraction renforcée du total TTC des devis, notamment `TOTAL DU DEVIS € T.T.C.`.
- Présentation : avis simple et clair avec fiabilité, sans noyer l'utilisateur sous des fiches non pertinentes.

## Lancement local

Double-cliquer sur :

`LANCER_CLAIMSPILOT_EXPERT_WINDOWS.bat`

## Streamlit Cloud

Fichier principal :

`streamlit_app.py`

Python : 3.12
