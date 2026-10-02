# Maintenance de la plateforme et transfert des données

Espace d'administration : **Administration › Données & maintenance** (`/admin/donnees-maintenance`),
réservé à l'administrateur principal (rôle `admin` ; les modérateurs n'y ont pas accès).

## 1. Maintenance — déconnexion de tous les utilisateurs

| Phase | Période | Membres et modérateurs | Administrateur principal |
|---|---|---|---|
| Annonce | de l'envoi au début du verrouillage (100 − part %) | fenêtre fermable (message + décompte), puis bandeau rouge | bandeau orange + « Annuler » |
| Verrouillage | dernière part de la durée (80 % par défaut) | écran plein, non fermable (ni Échap, ni clic, page inerte), décompte mm:ss | idem |
| Maintenance | à l'échéance, jusqu'à la réactivation | déconnexion forcée ; API → **503** ; connexion, inscription, connexion TikTok et chat temps réel refusés | bandeau rouge + « Réactiver les connexions » |

- Réglages : message (obligatoire, 1 000 caractères max), durée 1 à 120 min (5 par défaut), part verrouillée 0 à 100 % (80 par défaut).
- Décompte calé sur l'heure du serveur (`maintenant_serveur`) ; état relu toutes les 15 s et au retour sur l'onglet.
- Annulation possible avant l'échéance : personne n'est déconnecté.
- Réactivation : « sessions valides après » = échéance ; les sessions ouvertes avant restent invalides (401), chacun se reconnecte
  (le jeton porte son heure d'ouverture, champ `ouv`).
- L'administrateur principal n'est jamais bloqué.

Routes : `GET /api/maintenance/etat` (public, sans donnée sensible) ;
`GET|POST /api/plateforme/deconnexion-generale`, `POST …/annuler`, `POST …/reactiver` (administrateur principal).

**Non bloqué** (aucune session) : webhook PawaPay `POST /api/payments/pawapay/webhooks/deposits/{secret}`,
retour TikTok `GET /api/auth/tiktok/callback` (+ `/config`, `/start`), `/api/health`, `/api/appearance`,
`/api/maintenance/etat`, `/api/stats/visit`, `/api/stats/public`, `GET /api/testimonials`, `GET /api/profile-options`,
`GET /api/gifts`, `GET /api/subscriptions/plans`, `GET /api/users/{id}/rating-summary`, `/api/vidal/…` (secret propre),
`/api/plateforme/transfert/taches/…` et `/api/plateforme/transfert/restauration-initiale`, et les tâches de fond
(rapprochement PawaPay chaque minute, VIDAL, floutage) : un paiement confirmé pendant la maintenance est bien appliqué.
La page de retour de paiement d'un membre (`GET /api/payments/pawapay/{id}`) exige une session : elle attend la réactivation.

Stockage : `maf_maintenance_plateforme` (document `_id: "etat"`) et `maf_maintenance_plateforme_journal`.

## 2. Export / import complets (changement de cluster MongoDB)

- **Export** : toutes les collections `maf_*` + leurs index, en Extended JSON canonique (types conservés), dans un ZIP
  chiffré AES-256-GCM (clé scrypt d'une phrase secrète ≥ 12 caractères), par blocs de 1 Mo, signé par le serveur
  (HMAC dérivé de `JWT_SECRET`). Tâche de fond avec progression ; fichier `.baexport` téléchargeable **une seule fois**,
  effacé au bout d'une heure sinon. Mot de passe de l'administrateur redemandé ; tout est journalisé
  (`maf_journal_transferts`).
- **Import** : « Base vide uniquement » (tolère ce que crée le démarrage : compte admin d'amorçage, formules et cadeaux
  par défaut, compteur de visites, réglage VIDAL, journaux) ou « Remplacer » (taper `REMPLACER`). Fichier entièrement
  vérifié avant toute écriture, insertion par lots de 1 000, index recréés, rapport de comparaison des nombres.
- **Restauration initiale** (`/restauration-initiale`, sans session) : seulement si la base n'a **aucun compte**, si
  `JWT_SECRET` n'a pas sa valeur par défaut, si le fichier est signé par un serveur au même `JWT_SECRET`, et si
  l'e-mail/mot de passe sont ceux d'un administrateur actif du fichier (vérifiés avant écriture).

## Mode d'emploi du transfert

1. Ancien serveur : *Données & maintenance* › annoncer une maintenance (ex. 5 min) ; attendre l'échéance.
2. *Exporter toutes les données* (phrase secrète notée en lieu sûr) › télécharger le `.baexport`.
3. Atlas : créer l'utilisateur et autoriser l'accès réseau sur le nouveau cluster, copier son adresse `mongodb+srv://…`.
4. Render › service `meetafrican-backend` › *Environment* : remplacer **`MONGO_URL`** (ne pas toucher `JWT_SECRET`,
   `MONGO_DB_NAME`, `MONGO_COLLECTION_PREFIX`) › enregistrer et redéployer.
5. Nouveau serveur : se connecter avec le compte `ADMIN_BOOTSTRAP_EMAIL` s'il est défini, puis *Importer* (mode
   « Base vide uniquement ») ; sinon, page de connexion › « Restaurer une sauvegarde ».
6. Se reconnecter avec le compte administrateur de l'ancienne base et vérifier le rapport. La maintenance annoncée
   à l'étape 1 fait partie du fichier : elle est reprise par la nouvelle base (les membres restent bloqués).
   Cliquer enfin sur *Réactiver les connexions* : chacun se reconnecte.

Entre les étapes 4 et 5, la nouvelle base n'a aucun membre : personne ne peut se connecter, mais une inscription
reste possible ; si quelqu'un s'inscrit entre-temps, le mode « Base vide uniquement » refuse l'import (utiliser alors
« Remplacer », qui efface ce compte).
