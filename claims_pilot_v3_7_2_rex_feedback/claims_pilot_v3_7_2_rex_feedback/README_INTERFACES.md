# ClaimsPilot V3.6.8 - interfaces separees

Cette version separe clairement les usages :

## 1. Interface expert locale Windows
Lancer :

```text
LANCER_CLAIMSPILOT_EXPERT_WINDOWS.bat
```

ou, par compatibilite :

```text
LANCER_CLAIMSPILOT_WINDOWS.bat
```

Cette interface lance `app.py` et donne acces aux ecrans complets :
- Qualification
- Elements recus / a obtenir
- Analyse photos
- Sources metier
- Carbone
- Pack agent
- Exports

## 2. Demo client locale
Lancer :

```text
LANCER_DEMO_CLIENT_WINDOWS.bat
```

Cette interface lance `demo_client.py`.

## 3. Streamlit Cloud
Fichier principal :

```text
streamlit_app.py
```

Ce fichier pointe volontairement vers la demo client, et non vers l'interface expert.

## Important
Ne pas selectionner les fichiers `.bat` dans Streamlit Cloud.
