# Abonnements, sessions et sauvegardes

Spécification commune validée le 02/10/2026. Pour beAuthentik, le « locataire » est le **membre abonné**.
Réglages : Administration › **Sessions, sauvegardes & cycle de vie** (administrateur principal) et fiche membre.

## A. Grâce après échéance impayée
- 3 jours par défaut (paramètre de la plateforme, 0 à 30), réglable pour chaque membre dans sa fiche.
- « Renouveler la grâce (+3 j) » : 3 fois au plus par échéance (le compteur repart à zéro avec la nouvelle échéance). Journalisé.
- Pendant la grâce : accès normal + bandeau rouge « Abonnement expiré — N jour(s) de grâce restant(s) — Renouveler ».
- Après la grâce, à la requête suivante (contrôle serveur, à l'heure exacte) : la fonction payante est coupée, c'est-à-dire
  le visage en clair sur les photos des autres membres (découverte, recherche, fiches profil, liste des conversations).
  Le membre garde l'usage gratuit du site ; bandeau orange avec les dates du cycle de vie.

## B. Sessions simultanées
- 5 sessions par compte (1 à 20). À la connexion suivante, la session la moins récemment active est fermée ; l'appareil voit
  « Session fermée : nombre maximal d'appareils atteint pour ce compte. »
- Mon compte › **Sécurité & sessions** : liste (appareil, IP, ouverture, dernière activité) et « Fermer ».
  Administration : nombre de sessions par compte, fermeture dans la fiche membre.

## Déconnexion après inactivité
- En secondes : 0 = désactivée, sinon 60 à 86 400 (plateforme), surcharge par membre (administrateur) ; le membre peut seulement réduire.
- Avertissement « Rester connecté » ; contrôle serveur (dernière activité par session, au plus une écriture par minute ;
  les rafraîchissements automatiques portent l'en-tête `X-BA-Fond` et ne comptent pas comme une activité).

## D. Dernière sauvegarde
« Dernière sauvegarde générale : JJ/MM/AAAA HH:MM » dans Mon compte, Sécurité & sessions et en pied de page de l'administration
(« Aucune sauvegarde enregistrée » en orange sinon). Pas de sauvegarde propre à chaque membre.

## E. Sauvegarde générale automatique
Variables d'environnement (Render) :

| Variable | Rôle |
|---|---|
| `SAUVEGARDE_AUTO_PHRASE` | phrase de chiffrement (12 caractères min.) — sans elle : désactivée + alerte |
| `SAUVEGARDE_AUTO_JETON` | secret de l'en-tête `X-Sauvegarde-Jeton` |
| `BEAUTHENTIK_SAUVEGARDES_R2_ACCOUNT_ID`, `_R2_ACCESS_KEY_ID`, `_R2_SECRET_ACCESS_KEY` | facultatives : sinon `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` sont réutilisées |
| `BEAUTHENTIK_SAUVEGARDES_BUCKET` | facultative : sinon le bucket privé `R2_BUCKET_DOCUMENTS` |
| `BEAUTHENTIK_SAUVEGARDES_PREFIXE` | dossier dans le bucket (défaut `sauvegardes-beauthentik/`) |

Cron Job Render (chaque nuit) :
`curl -fsS -X POST -H "X-Sauvegarde-Jeton: $SAUVEGARDE_AUTO_JETON" https://api.beauthentik.net/api/sauvegarde-auto/declencher`
— réponse 202 immédiate, une seule sauvegarde réussie par jour (UTC), puis la tâche du cycle de vie.
Même format `.baexport` et même chiffrement que l'export manuel. Rétention 7 quotidiennes + 4 hebdomadaires + 12 mensuelles.
Échec : alerte WhatsApp/SMS aux administrateurs, plus un e-mail à leur adresse (si le service d'envoi est réglé) ;
réussite : rapport par e-mail seulement ; alerte dans l'administration si la dernière réussite a plus de 26 h. Restauration depuis la liste R2 (mode Remplacer, mot de passe + « REMPLACER »).

## C. Cycle de vie du non-renouvellement
J+103 avertissement · J+110 suspension (compte masqué, accès limité au renouvellement ; un paiement lève la suspension) ·
J+112 avertissement · J+113 archive chiffrée du membre sur R2 (`archives-locataires/<id>/`), relue et vérifiée, puis
suppression du compte et de ses données (s'il revient, nouvelle inscription). Échec : rien n'est supprimé, alerte.
Archives conservées 1 an (réglable) puis effacées avec les médias du membre. Réouverture : manuelle par l'administrateur
depuis l'archive (frais de réouverture affichés, encaissement manuel). Interrupteur + mode simulation + rapports quotidiens.
Exclus : administrateurs, modérateurs, comptes de test, comptes désactivés manuellement, membres jamais abonnés.
À la mise en service, les échéances anciennes repartent de J+103 (aucune suspension ni suppression sans avertissement).
Avertissements J+103, J+110 et J+112 : WhatsApp puis SMS, plus un e-mail aux membres qui ont une adresse (une seule fois
chacun ; statut de l'e-mail noté dans le journal du cycle de vie). Rapport quotidien : WhatsApp/SMS + e-mail détaillé.

## Envoi des e-mails de la plateforme
Écran « Envoi des e-mails » (administrateur principal, `/admin/envoi-emails`). Service au choix : Resend, ZeptoMail (Zoho,
région .com / .eu / .in), Brevo, SMTP, ou Désactivé (par défaut). Les e-mails s'ajoutent toujours à WhatsApp / SMS.
- Clés API et mot de passe SMTP chiffrés en base (Fernet dérivé de `JWT_SECRET`), jamais renvoyés au navigateur ;
  champ secret laissé vide = valeur conservée.
- SMTP : bloqué sur les services Render gratuits (ports 25, 465, 587) ; fonctionne avec l'offre Starter, sauf le port 25
  (refusé par l'écran). Les 3 autres services passent par HTTPS (port 443).
- « Envoyer un essai » utilise les réglages enregistrés et affiche le message d'erreur du fournisseur.
- Journal des modifications (qui, quand, quel fournisseur, quels champs — jamais la clé) : `maf_email_reglages_journal` ;
  journal des envois (ENVOYE / ECHEC / NON_CONFIGURE) : `maf_emails_journal`.
- Repli quand rien n'est réglé dans l'écran : `RESEND_API_KEY` + `RESEND_EXPEDITEUR`, puis `PLATEFORME_SMTP_*` (ou
  `SMTP_*`), puis `BREVO_API_KEY`, puis `ZEPTOMAIL_API_KEY` (+ `ZEPTOMAIL_HOTE`), avec `EMAIL_EXPEDITEUR`.
- Pas de réglage par membre : seul le niveau plateforme existe.
