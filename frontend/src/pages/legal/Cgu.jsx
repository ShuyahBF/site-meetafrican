import LegalLayout, { CONTACT_EMAIL } from "@/pages/legal/LegalLayout";
import { PAYMENT_METHODS } from "@/components/PaymentMethods";

// Conditions générales d'utilisation. Chaque règle décrite ici correspond à
// un fonctionnement réel du site (vérification, flou des vidéos,
// signalements, abonnements sans renouvellement automatique…).
const SECTIONS = [
  {
    id: "objet",
    title: "Objet et acceptation",
    body: (
      <>
        <p>
          beAuthentik (le « Site », accessible sur https://beauthentik.net) est un service de rencontre en ligne
          destiné aux personnes africaines et de la diaspora. Les présentes conditions générales d'utilisation (les
          « CGU ») fixent les règles d'utilisation du Site par ses membres.
        </p>
        <p>
          En créant un compte, vous acceptez sans réserve les présentes CGU ainsi que notre{" "}
          <a href="/confidentialite" className="font-semibold text-primary">politique de confidentialité et de service</a>.
          La date et la version acceptées sont enregistrées avec votre compte.
        </p>
      </>
    ),
  },
  {
    id: "acces",
    title: "Accès au service et compte",
    body: (
      <>
        <ul>
          <li>Le Site est <strong>strictement réservé aux personnes majeures (18 ans et plus)</strong>. La date de naissance est contrôlée à l'inscription.</li>
          <li>Un seul compte par personne. Les informations fournies (nom, âge, photos…) doivent être exactes et vous concerner.</li>
          <li>Vous êtes responsable de la confidentialité de votre mot de passe et de toute activité réalisée depuis votre compte.</li>
          <li>L'inscription, la création du profil, les swipes, les matchs et la consultation des Moments sont gratuits. Certaines fonctionnalités sont réservées aux membres Premium.</li>
        </ul>
      </>
    ),
  },
  {
    id: "authenticite",
    title: "Vérification d'identité et authenticité",
    body: (
      <>
        <p>
          Pour garantir une communauté de personnes réelles, vous pouvez (et, pour publier des vidéos, devez) faire
          vérifier votre identité en envoyant une photo de votre pièce d'identité (carte nationale, passeport ou
          permis). Elle est analysée automatiquement puis, en cas de doute, par un membre de notre équipe. Une fois
          vérifiée, le badge <strong>« identité vérifiée »</strong> s'affiche sur votre profil.
        </p>
        <p>
          Votre pièce d'identité n'est <strong>jamais visible par les autres membres</strong>. Les faux profils, l'usurpation
          d'identité et l'utilisation de photos d'autrui sont interdits et entraînent la suppression du compte.
        </p>
      </>
    ),
  },
  {
    id: "contenus",
    title: "Photos, vidéos et contenus publiés",
    body: (
      <>
        <ul>
          <li><strong>Photos</strong> : chaque photo est analysée avant publication (automatiquement, puis par un humain en cas de doute). Une photo approuvée reçoit un filigrane beAuthentik ; pour les visiteurs sans abonnement, le visage est masqué.</li>
          <li><strong>Vidéos (« Moments »)</strong> : réservées aux identités vérifiées, 60 secondes maximum. Chaque vidéo est compressée puis <strong>entièrement floutée et sans son</strong> pour l'ensemble des membres. La version claire n'est montrée qu'à vos matchs et aux membres vérifiés dont vous avez accepté la demande — accès que vous pouvez retirer à tout moment.</li>
          <li>Vous restez propriétaire de vos contenus. Vous accordez à beAuthentik le droit de les héberger, de les transformer (compression, flou, filigrane) et de les afficher sur le Site, pour la seule durée de leur publication.</li>
          <li>Vous pouvez supprimer vos photos et vidéos à tout moment depuis votre profil.</li>
        </ul>
      </>
    ),
  },
  {
    id: "conduite",
    title: "Règles de conduite",
    body: (
      <>
        <p>Sont notamment interdits, sur le profil, dans les vidéos, les commentaires et les messages :</p>
        <ul>
          <li>le harcèlement, les menaces, les insultes et les propos discriminatoires ;</li>
          <li>les contenus sexuellement explicites, violents ou choquants, et tout contenu impliquant des mineurs ;</li>
          <li>les arnaques, les demandes d'argent, de transferts ou de codes Mobile Money, la prostitution et les sollicitations commerciales ;</li>
          <li>le partage de coordonnées ou d'images d'un tiers sans son accord ;</li>
          <li>le spam, les envois automatisés et toute tentative de contourner les protections du Site (flou des vidéos, masquage des visages…).</li>
        </ul>
      </>
    ),
  },
  {
    id: "interactions",
    title: "Matchs, messagerie et signalements",
    body: (
      <>
        <p>
          Une conversation s'ouvre uniquement lorsque l'intérêt est réciproque (match). Vous pouvez signaler un
          profil ou une vidéo en un clic : une vidéo signalée par plusieurs membres est retirée automatiquement en
          attendant l'examen de l'équipe de modération.
        </p>
      </>
    ),
  },
  {
    id: "paiements",
    title: "Abonnements, portefeuille et cadeaux",
    body: (
      <>
        <ul>
          <li>Les prix sont affichés en FCFA, toutes taxes comprises, sur la page Tarifs. L'abonnement Premium est souscrit pour la durée choisie (semaine, mois, année…) et <strong>ne se renouvelle pas automatiquement</strong>.</li>
          <li>Moyens de paiement acceptés : {PAYMENT_METHODS.map((m) => m.name).join(", ")}. Les paiements Mobile Money sont traités par notre prestataire de paiement PawaPay ; beAuthentik n'a jamais accès à vos codes secrets.</li>
          <li>L'abonnement est activé dès la confirmation du paiement par l'opérateur. Si vous êtes débité sans activation, contactez-nous à {CONTACT_EMAIL} avec la référence du paiement : nous régularisons la situation.</li>
          <li>Sauf disposition légale contraire, une période d'abonnement commencée n'est pas remboursable, de même que les cadeaux déjà envoyés.</li>
          <li>Le portefeuille prépayé sert uniquement à envoyer des cadeaux sur le Site. Les points de parrainage n'ont aucune valeur monétaire et ne sont pas échangeables contre de l'argent.</li>
        </ul>
      </>
    ),
  },
  {
    id: "moderation",
    title: "Modération, suspension et suppression",
    body: (
      <>
        <p>
          En cas de non-respect des présentes CGU, beAuthentik peut retirer un contenu, suspendre ou désactiver un
          compte, sans remboursement des sommes déjà engagées. Vous pouvez demander la suppression de votre compte à
          tout moment en écrivant à {CONTACT_EMAIL}.
        </p>
      </>
    ),
  },
  {
    id: "prudence",
    title: "Conseils de sécurité",
    body: (
      <ul>
        <li>Ne transmettez jamais d'argent, de code Mobile Money ou de document personnel à un membre.</li>
        <li>Pour une première rencontre, choisissez un lieu public et prévenez un proche.</li>
        <li>Signalez tout comportement suspect : c'est anonyme et notre équipe l'examine.</li>
      </ul>
    ),
  },
  {
    id: "responsabilite",
    title: "Responsabilité",
    body: (
      <p>
        beAuthentik met en relation ses membres et met en œuvre des moyens raisonnables (vérification d'identité,
        modération, signalements) pour la sécurité de la communauté, sans pouvoir garantir le comportement de chaque
        membre ni l'issue des rencontres. Chaque membre est seul responsable des contenus qu'il publie et de ses
        échanges avec les autres membres.
      </p>
    ),
  },
  {
    id: "propriete",
    title: "Propriété intellectuelle",
    body: (
      <p>
        La marque beAuthentik, le logo, le design et le code du Site sont protégés. Toute reproduction sans
        autorisation est interdite. Les marques des opérateurs de paiement citées appartiennent à leurs titulaires.
      </p>
    ),
  },
  {
    id: "modifications",
    title: "Modification des CGU et droit applicable",
    body: (
      <p>
        beAuthentik peut faire évoluer les présentes CGU ; la version en vigueur et sa date figurent en tête de cette
        page, et les membres sont informés des changements importants. Les CGU sont soumises au droit du Burkina Faso.
        En cas de litige, une solution amiable sera recherchée avant toute action devant les juridictions
        compétentes.
      </p>
    ),
  },
];

export default function Cgu() {
  return (
    <LegalLayout
      title="Conditions générales d'utilisation"
      intro="Bienvenue sur beAuthentik. Ces conditions expliquent, simplement, comment utiliser le site : qui peut s'inscrire, ce qui est autorisé ou non, et comment fonctionnent les abonnements."
      sections={SECTIONS}
      other={{ to: "/confidentialite", label: "Confidentialité →" }}
    />
  );
}
