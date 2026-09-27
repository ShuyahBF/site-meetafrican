import LegalLayout, { CONTACT_EMAIL } from "@/pages/legal/LegalLayout";

// Politique de confidentialité et de service. Les durées de conservation
// indiquées ici sont celles appliquées par le code :
//   - journal d'activité (IP)  : purge automatique après 12 mois (index TTL, backend/db.py)
//   - IP des visites           : purge automatique après 31 jours (index TTL, backend/db.py)
//   - liens vers les vidéos claires : expiration après 2 h (backend/routes/videos.py)
// Toute modification de ces réglages doit être reportée ici.
const RETENTION = [
  ["Compte et profil (nom, âge, ville, bio, centres d'intérêt…)", "Tant que le compte existe ; supprimés avec le compte."],
  ["Photos de profil", "Jusqu'à leur suppression par vous, par la modération, ou la suppression du compte."],
  ["Pièce d'identité", "Stockage privé, jamais montrée aux membres. Conservée tant que le compte existe (preuve de la vérification), supprimée avec le compte."],
  ["Vidéos (« Moments »)", "Version floutée publique et version claire privée, jusqu'à suppression par vous, la modération ou la suppression du compte. Les liens vers la version claire expirent après 2 heures."],
  ["Messages et interactions (matchs, J'aime, commentaires)", "Tant que les comptes concernés existent ; supprimés avec le compte."],
  ["Position (seulement si vous activez « Autour de moi »)", "Arrondie à environ 1 km, remplacée à chaque mise à jour, jamais montrée aux autres membres (seule une distance approximative l'est). Supprimée dès que vous cliquez sur « Ne plus partager ma position » ou avec le compte."],
  ["Journal d'activité (adresse IP, action réalisée, navigateur, date)", "12 mois, puis effacement automatique."],
  ["Adresse IP d'inscription et de dernière connexion", "Tant que le compte existe."],
  ["Adresse IP des visites de la page d'accueil", "31 jours (sert uniquement à ne compter qu'une visite par jour), puis effacement automatique. Seul le nombre total de visites est conservé."],
  ["Paiements et abonnements (montant, date, référence, IP)", "Durée imposée par les obligations comptables et fiscales (jusqu'à 10 ans)."],
  ["Signalements et décisions de modération", "Le temps nécessaire au traitement et à la prévention des abus."],
];

const SECTIONS = [
  {
    id: "responsable",
    title: "Qui est responsable de vos données ?",
    body: (
      <p>
        L'éditeur du site beAuthentik (https://beauthentik.net) est responsable du traitement de vos données
        personnelles. Pour toute question ou demande : <strong>{CONTACT_EMAIL}</strong>.
      </p>
    ),
  },
  {
    id: "donnees",
    title: "Données collectées",
    body: (
      <ul>
        <li><strong>Compte</strong> : nom affiché, email ou téléphone, mot de passe (stocké sous forme chiffrée irréversible), genre, date de naissance.</li>
        <li><strong>Profil</strong> : photos, bio, ville, pays, profession, centres d'intérêt, type de relation recherchée, situation vis-à-vis des enfants.</li>
        <li><strong>Vérification</strong> : photo de votre pièce d'identité.</li>
        <li><strong>Contenus et échanges</strong> : vidéos, légendes, commentaires, messages, J'aime, swipes, matchs, cadeaux, signalements, notes.</li>
        <li><strong>Paiements</strong> : formule, montant, date, référence et statut du paiement, numéro Mobile Money si vous le communiquez au prestataire.</li>
        <li><strong>Données techniques</strong> : adresse IP, navigateur, date et nature de chaque action (voir « Traçabilité » ci-dessous), date de dernière connexion.</li>
      </ul>
    ),
  },
  {
    id: "finalites",
    title: "Pourquoi nous les utilisons",
    body: (
      <ul>
        <li>Fournir le service : profils, découverte, recherche, Moments, messagerie, abonnements.</li>
        <li>Garantir l'authenticité des membres (vérification d'identité, modération des photos).</li>
        <li>Assurer la sécurité : lutte contre les faux profils, les arnaques et les abus, traitement des signalements.</li>
        <li>Traiter les paiements et répondre aux obligations comptables.</li>
        <li>Mesurer la fréquentation du site (compteur de visites agrégé).</li>
      </ul>
    ),
  },
  {
    id: "visibilite",
    title: "Ce que voient les autres membres",
    body: (
      <>
        <p>Les autres membres peuvent voir : votre nom affiché, votre âge (jamais la date de naissance exacte), votre ville et votre pays, votre bio et vos informations de profil, vos photos approuvées (visage flouté pour les non-abonnés), vos vidéos (visage flouté et sans son, sauf accès accordé), une distance approximative en km si vous utilisez « Autour de moi », votre statut « en ligne » ou votre dernière connexion, votre réactivité aux messages et vos compteurs (J'aime, coups de cœur).</p>
        <p>Ils ne voient <strong>jamais</strong> : votre email, votre téléphone, votre pièce d'identité, votre position exacte, votre adresse IP ni vos paiements.</p>
      </>
    ),
  },
  {
    id: "tracabilite",
    title: "Traçabilité et adresses IP",
    body: (
      <p>
        Pour la sécurité des membres et la lutte contre la fraude, chaque action qui modifie des données (inscription,
        connexion, abonnement, paiement, publication, message, J'aime, signalement…) est enregistrée avec l'adresse IP
        de son auteur, dans un journal accessible uniquement aux administrateurs et modérateurs. Ce journal est
        <strong> effacé automatiquement au bout de 12 mois</strong>. Votre propre adresse IP est affichée sur la page
        d'accueil, à titre d'information.
      </p>
    ),
  },
  {
    id: "conservation",
    title: "Durées de conservation",
    body: (
      <div className="overflow-hidden rounded-2xl ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3">Données</th>
              <th className="px-4 py-3">Durée de conservation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {RETENTION.map(([what, how]) => (
              <tr key={what} className="align-top">
                <td className="px-4 py-3 font-semibold text-ink">{what}</td>
                <td className="px-4 py-3">{how}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
  },
  {
    id: "securite",
    title: "Sécurité",
    body: (
      <ul>
        <li>Connexions chiffrées (HTTPS) sur l'ensemble du site.</li>
        <li>Mots de passe stockés sous forme hachée, jamais en clair.</li>
        <li>Pièces d'identité et vidéos claires dans un stockage privé, accessible uniquement via des liens temporaires.</li>
        <li>Accès au back-office réservé aux administrateurs et modérateurs.</li>
      </ul>
    ),
  },
  {
    id: "navigateur",
    title: "Cookies et stockage local",
    body: (
      <p>
        Le site n'utilise <strong>aucun cookie publicitaire ni traceur publicitaire</strong>. Votre navigateur conserve
        uniquement votre jeton de connexion (pour rester connecté) et quelques préférences (critères de recherche,
        visite déjà comptée), supprimés à la déconnexion ou en effaçant les données du site.
      </p>
    ),
  },
  {
    id: "droits",
    title: "Vos droits",
    body: (
      <>
        <p>
          Vous pouvez à tout moment accéder à vos données, les rectifier (la plupart directement depuis « Mon
          profil »), demander leur suppression ou une copie, et vous opposer à certains traitements. Écrivez-nous à{" "}
          <strong>{CONTACT_EMAIL}</strong> : nous répondons dans un délai de 30 jours. La suppression du compte
          entraîne celle du profil, des photos, des vidéos, de la pièce d'identité et des messages, sous réserve des
          données que la loi nous oblige à conserver (paiements).
        </p>
        <p>
          Vous pouvez également saisir l'autorité de protection des données de votre pays (au Burkina Faso : la
          Commission de l'Informatique et des Libertés, CIL).
        </p>
      </>
    ),
  },
  {
    id: "service",
    title: "Nos engagements de service",
    body: (
      <ul>
        <li><strong>Authenticité</strong> : vérification d'identité et modération des photos avant publication.</li>
        <li><strong>Vie privée</strong> : visage flouté par défaut sur les vidéos, visibles en clair uniquement sur votre accord, et accès révocable.</li>
        <li><strong>Modération</strong> : les signalements sont examinés par l'équipe ; une vidéo signalée plusieurs fois est retirée en attendant la décision.</li>
        <li><strong>Paiements</strong> : abonnements sans renouvellement automatique ; tout paiement débité sans activation est régularisé sur simple demande.</li>
        <li><strong>Disponibilité</strong> : nous faisons notre possible pour que le site soit accessible en permanence, hors opérations de maintenance.</li>
        <li><strong>Assistance</strong> : {CONTACT_EMAIL}, réponse sous 30 jours au plus, en pratique bien plus rapidement.</li>
      </ul>
    ),
  },
  {
    id: "mineurs",
    title: "Mineurs",
    body: <p>Le site est interdit aux moins de 18 ans. Tout compte d'une personne mineure est supprimé dès que nous en avons connaissance.</p>,
  },
  {
    id: "evolution",
    title: "Évolution de cette politique",
    body: <p>Cette politique peut évoluer avec le service ; la version en vigueur et sa date figurent en tête de page, et les membres sont informés des changements importants.</p>,
  },
];

export default function Confidentialite() {
  return (
    <LegalLayout
      title="Politique de confidentialité et de service"
      intro="Nous prenons votre vie privée au sérieux : voici, en clair, quelles données nous collectons, pourquoi, qui peut les voir, combien de temps nous les gardons et comment exercer vos droits."
      sections={SECTIONS}
      other={{ to: "/cgu", label: "Conditions d'utilisation →" }}
    />
  );
}
