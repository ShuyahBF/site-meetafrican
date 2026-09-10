# Portage VIDAL vers Sawali Smart Systems — à faire

## Contexte

Le module VIDAL (sécurisation de prescription, posologie, admin médecins,
suivi des logs) a été prototypé et validé visuellement dans **ce dépôt**
(`ShuyahBF/site-meetafrican`), sous la route cachée `/secure`, faute de
crédits Emergent.sh disponibles pour prévisualiser directement sur
l'environnement cible. Ce n'est **pas** l'emplacement final : c'est un
banc d'essai.

**La destination réelle est le portail Sawali Smart Systems**, sur la
branche `Site-SawaliSmartSystems` du job Emergent `sawali-portal`
(stack FastAPI + React + MongoDB Atlas, base `vidal`).

## À faire plus tard

Porter les fonctionnalités validées ici vers `Site-SawaliSmartSystems`,
**via prompt + patch git envoyé au job Emergent `sawali-portal`** — même
méthode déjà utilisée pour les autres correctifs Sawali (patch généré,
join en un seul `git am`, déploiement direct sans re-vérification quand
déjà validé côté utilisateur). Ce n'est pas un copier-coller direct : le
code React/CSS de ce dépôt (`frontend/src/secure/`) sert de référence
visuelle et fonctionnelle, mais l'intégration réelle demande une vraie
intégration backend (auth, dossiers patients, vrais appels API VIDAL,
collections MongoDB `vidal.*` documentées dans le code) — absente ici où
tout est simulé côté client.

## Pull requests de référence (dépôt `site-meetafrican`)

| PR | Contenu |
|----|---------|
| [#2](https://github.com/ShuyahBF/site-meetafrican/pull/2) | Route cachée `/secure` avec sidebar (Sécurisation / Posologie / Admin médecins) |
| [#3](https://github.com/ShuyahBF/site-meetafrican/pull/3) | Sidebar responsive sur mobile (barre horizontale) |
| [#4](https://github.com/ShuyahBF/site-meetafrican/pull/4) | Sidebar en tiroir rétractable sur mobile (bouton ☰) |
| [#5](https://github.com/ShuyahBF/site-meetafrican/pull/5) | Fond opaque Posologie + en-tête Sécurisation compact au défilement |
| [#6](https://github.com/ShuyahBF/site-meetafrican/pull/6) | Thème clair (défaut) / sombre pilotable depuis la sidebar, notes VIDAL repliables réservées à l'admin, boutons d'action égaux/repliables |
| [#7](https://github.com/ShuyahBF/site-meetafrican/pull/7) | Journal des appels API VIDAL (page "Suivi des logs" dédiée, filtre par période, impression), bloc persistance MongoDB réservé à l'admin |

## Points à ne pas perdre au portage

- **Adresse MAC non capturable** depuis un navigateur (documenté dans le
  journal des logs) — ne pas tenter de la fabriquer côté Sawali non plus.
- Convention **texte saisi en bleu** (`--input-text` / `--accent`), distincte
  de la couleur des libellés.
- Thème clair par défaut, sombre en bascule explicite (ne pas dépendre de
  `prefers-color-scheme` seul).
- Notes techniques VIDAL et bloc persistance MongoDB : réservés à l'admin,
  masqués par défaut.
- Schémas VIDAL réels (voir le manuel d'intégration confidentiel déjà
  analysé) : `patient`, `prescription-lines`, `alert-types`,
  `posology-request` — les noms de champs et types d'énumération utilisés
  dans ce prototype sont vérifiés ligne à ligne contre le manuel, pas
  inventés.
- **Ordonnances PDF — deux versions distinctes, pas une seule** :
  - Celle imprimée/téléchargée par le médecin porte le **nom du patient en
    clair** (nécessaire à la pharmacie) et n'est jamais envoyée où que ce
    soit depuis le navigateur du médecin.
  - Celle archivée côté serveur (`ordonnance_pdf_ref`, stockée dans
    **Cloudflare R2**, bucket **dédié VIDAL** — séparé du bucket
    `meetafrican-documents` déjà utilisé sur cette infra) doit être une
    régénération avec **identité anonymisée** (ID patient ou nom masqué,
    même convention que l'historique) : c'est cette version que verrait un
    tiers scannant le QR de vérification, jamais le nom complet.

## État réel de l'infrastructure MongoDB Atlas (vérifié le 10/09/2026)

Le cluster `Cluster0` (celui déjà utilisé par `site_meetafrican`, `albarka`,
`bfmobility`) est **le cluster réel de production/dev partagé** — pas une
maquette. La base `vidal` y existe déjà et a été complétée à cette date :
les 6 collections documentées ci-dessus (`medecins`, `api_calls`,
`patients`, `patient_access_requests`, `patient_treatments`,
`securisation`) sont toutes créées (vides, sans données factices — seule
`securisation` préexistait, déjà vide). Le bucket Cloudflare R2 dédié
VIDAL, lui, **reste à créer** — aucun accès Cloudflare disponible depuis
cette session pour le faire.
