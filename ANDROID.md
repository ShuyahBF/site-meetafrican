# beAuthentik sur Android (application installable)

Le site beAuthentik est une **application installable** : icône sur l'écran d'accueil, ouverture plein écran, page « Pas de connexion »
quand Internet manque. Elle se met à jour toute seule (elle charge toujours la dernière version du site).

## 1. Installer tout de suite (sans Play Store)
Sur le téléphone, avec Chrome : ouvrir https://beauthentik.net, puis toucher **Installer l'application**
(sous le formulaire de connexion, ou dans *Réglages*), ou menu ⋮ de Chrome → *Installer l'application*.

## 2. Fabriquer le fichier Android avec PWABuilder (par clics, sans programmation)
1. Ouvrir **https://www.pwabuilder.com**, saisir l'adresse du site : `https://beauthentik.net`, cliquer **Start**.
2. Vérifier que « Manifest » et « Service Worker » sont verts, puis **Package for stores** → **Android**.
3. Renseigner :
   - **Nom de l'application** : `beAuthentik`
   - **Identifiant du paquet (Package ID)** : `com.sawali.beauthentik` (à ne plus jamais changer)
   - laisser le reste par défaut ; choisir de **créer une nouvelle clé de signature** si on le demande.
4. Cliquer **Generate** puis **télécharger le fichier ZIP**.
5. **Garder précieusement le ZIP, surtout le fichier de clé (.keystore) et ses mots de passe** : sans eux, impossible de mettre l'application à jour
   sur le Play Store. Les copier à deux endroits sûrs (clé USB, coffre-fort de mots de passe).
6. Dans le ZIP, ouvrir le fichier `assetlinks.json` (ou, dans la Play Console, *Intégrité de l'application*) et **copier l'empreinte SHA-256**
   (une suite du type `07:30:35:B9:…`). **Donner cette empreinte à Claude** : elle est ajoutée dans `frontend/public/.well-known/assetlinks.json`.
   Sans elle, l'application affiche une barre d'adresse en haut.
7. Déposer le fichier `.aab` dans la **Play Console** (fiche de l'application, politique de confidentialité : https://beauthentik.net/confidentialite).

## Règle de sécurité
**Ne jamais envoyer** le fichier de clé (.keystore) ni les mots de passe dans le chat, par e-mail ou dans le dépôt GitHub.
Seule l'**empreinte SHA-256** peut être donnée (elle n'est pas secrète).

## Contenu technique (pour mémoire)
- `frontend/public/manifest.json` : nom, icônes (192, 512, 512 « maskable »), couleurs, plein écran.
- `frontend/public/sw.js` : affiche `offline.html` quand Internet manque (rien d'autre n'est mis en cache).
- `frontend/public/.well-known/assetlinks.json` : lien site ↔ application Android (`[]` tant que l'empreinte n'est pas fournie).
- `frontend/src/components/InstallerApplication.jsx` : bouton « Installer l'application » (connexion et Réglages).
