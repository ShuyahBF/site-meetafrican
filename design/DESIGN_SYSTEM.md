# Charte graphique — MeetAfrican

Source : 22 écrans générés avec **Stitch AI** (Google), exportés en HTML + Tailwind CSS,
reçus le 2026-08-28 et rangés dans `design/stitch-exports/`.

## Inventaire des écrans

| # | Écran | Dossier |
|---|-------|---------|
| 01 | Bienvenue / onboarding | `01-bienvenue` |
| 02–05 | Inscription / connexion (4 étapes) | `02-inscription-connexion-1` … `05-inscription-connexion-4` |
| 06–08 | Découverte / accueil (swipe, 3 variantes) | `06-decouverte-1` … `08-decouverte-3` |
| 09 | Match ("C'est un Match !") | `09-matching` |
| 10 | Recherche avancée / filtres | `10-recherche-avancee` |
| 11–14 | Profil (4 variantes) | `11-profil-1` … `14-profil-4` |
| 15–16 | Gestion des photos de profil | `15-gestion-photos-profil-1`, `16-gestion-photos-profil-2` |
| 17–18 | Chat / messages | `17-chat-messages-1`, `18-chat-messages-2` |
| 19 | Sélection d'abonnement (Premium) | `19-selection-abonnement` |
| 20 | Paramètres de notifications | `20-parametres-notifications` |
| 21–22 | Administration (back-office) | `21-administration-1`, `22-administration-2` |

Chaque dossier contient `code.html` (le mockup HTML/Tailwind généré par Stitch) et
`screen.png` (capture visuelle).

## Tokens extraits

Stitch a généré chaque écran de façon quasi indépendante : les tokens varient légèrement
d'un écran à l'autre. Voici ce qui ressort une fois comparé sur les 22 écrans.

### Couleur primaire

| Zone de l'app | Couleur primaire | Écrans |
|---|---|---|
| Cœur de l'app (découverte, profil, chat, photos, recherche, abonnement, bienvenue) | **`#f4256a`** (rose/magenta) | 15 / 22 — couleur dominante, à retenir comme primaire officielle |
| Inscription / connexion | `#E94057` | 4 écrans (variante proche, même famille rose-rouge) |
| Écran de match | `#ee2b8c` | 1 écran (variante proche) |
| Paramètres de notifications | `#E57373` | 1 écran (rose plus doux) |
| Administration (back-office) | `#135bec` (bleu) | 2 écrans — palette volontairement différente pour distinguer le back-office |

**Recommandation** : unifier le produit utilisateur final sur `#f4256a` comme couleur
primaire unique (les variantes `#E94057` / `#ee2b8c` / `#E57373` sont assez proches pour
converger sans dénaturer le design). Garder le bleu `#135bec` uniquement pour
l'administration, qui est un espace visuellement séparé — à confirmer avec toi.

### Couleurs de fond (mode sombre par défaut)

- `background-light` : `#f8f5f6` (blanc cassé rosé)
- `background-dark` : `#221016` (bordeaux très sombre) — la plupart des écrans utilisent
  `class="dark"` par défaut, l'app est pensée "dark mode first"

### Typographie

- **Plus Jakarta Sans** — police principale de tout le produit utilisateur (400/500/700/800)
- **Manrope** — utilisée uniquement sur les 2 écrans d'administration
- Icônes : **Material Symbols Outlined** (Google)

### Forme / rayons

- `borderRadius.DEFAULT` : `1rem`
- `borderRadius.lg` : `1.25rem`–`2rem` (varie selon l'écran)
- `borderRadius.xl` : `1.5rem`–`3rem` (varie selon l'écran)
- `borderRadius.full` : `9999px` (boutons pilule, avatars)
- À normaliser dans le design system final : `lg = 1.5rem`, `xl = 2rem` semble le compromis
  le plus fréquent.

### Stack technique du mockup (à ne pas garder tel quel)

Les fichiers `code.html` sont des prototypes statiques : Tailwind chargé via CDN
(`cdn.tailwindcss.com`), aucune interactivité réelle, données factices en dur. Ils servent
de **référence visuelle et de structure de composants**, pas de code à déployer.

## Prochaine étape

Choisir la stack d'implémentation du vrai site (framework front, backend, base de
données, moteur de paiement pour les abonnements) avant de commencer à coder — voir
discussion avec l'utilisateur.
