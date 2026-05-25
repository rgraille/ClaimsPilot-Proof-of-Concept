# ClaimsPilot V3.7.2

Cette version ajoute un écran / pavé **REX - feed-back** pour capitaliser les écarts entre la réponse générée par l'application et la réponse expert attendue.

## Nouveautés

- Nouvel onglet expert : `REX / feed-back`.
- Nouveau pavé dans la démo client : `REX / feed-back pour améliorer l'algorithme`.
- Champs de saisie :
  - commentaire sur la réponse de l'application ;
  - réponse expert idéale / attendue ;
  - règle générale à ajouter ou corriger dans l'algorithme.
- Bouton `Télécharger le REX du cas d'usage (.txt)`.
- Le fichier REX contient :
  - les pièces analysées ;
  - le texte source réellement analysé ;
  - la réponse de l'application ;
  - le commentaire utilisateur ;
  - la réponse expert attendue ;
  - la règle générale proposée ;
  - la trace JSON complète.

## Usage recommandé

1. Lancer l'analyse du dossier.
2. Ouvrir l'onglet `REX / feed-back`.
3. Renseigner la réponse expert attendue et, si possible, la règle générale à intégrer.
4. Télécharger le fichier `.txt`.
5. Poster ce fichier dans ChatGPT pour transformer le retour terrain en amélioration de l'algorithme et en test de non-régression.
