import { useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, FOND } from "@/lib/api";
import { abonnerNonLus } from "@/hooks/useUnreadCount";
import {
  bipNouveauMessage,
  consommerCreditConversation,
  effacerCreditConversation,
  enregistrerPreferencesSon,
  installerDeverrouillageSon,
} from "@/lib/bipMessage";

/**
 * Bip sonore à l'arrivée d'un nouveau message (monté une seule fois dans App,
 * sans rien afficher).
 *
 * Fonctionnement :
 *  1. À la connexion d'un membre, ses préférences de son sont relues dans son
 *     profil (GET /api/me/settings) et copiées dans le navigateur (repli local).
 *  2. Le nombre de messages non lus est relevé toutes les 20 s (sondage partagé
 *     avec la pastille de la barre du bas). Le PREMIER relevé sert seulement de
 *     point de départ : aucun bip au chargement de la page.
 *  3. Ensuite, si le nombre de messages non lus AUGMENTE, un nouveau message a
 *     été reçu (les siens ne comptent jamais : le serveur ne compte que les
 *     messages des autres) -> bip, sauf en mode silencieux. Si la page
 *     Conversation a déjà sonné pour ce message (temps réel), on ne rejoue pas.
 * L'équipe (administrateur, modérateurs) n'a pas de messagerie : pas de bip.
 */
export default function BipNouveauMessage() {
  const { user } = useAuth();
  const reference = useRef(null); // nombre de messages non lus au relevé précédent

  // Autorise le son dès la première interaction (règle des navigateurs)
  useEffect(() => {
    installerDeverrouillageSon();
  }, []);

  const idMembre = user && user.role === "user" ? user.id : null;
  useEffect(() => {
    if (!idMembre) return undefined;
    // Nouveau compte connecté : repartir de zéro
    reference.current = null;
    effacerCreditConversation();

    // 1. Préférences enregistrées dans le profil -> copie locale
    apiClient.get("/me/settings", FOND).then((r) => enregistrerPreferencesSon(r.data)).catch(() => {});

    // 2 et 3. Surveillance du nombre de messages non lus
    return abonnerNonLus(({ messages }) => {
      const avant = reference.current;
      reference.current = messages;
      if (avant !== null) {
        // Nouveaux messages reçus depuis le relevé précédent (0 si rien ou si lus)
        const nouveaux = Math.max(0, messages - avant);
        // On retire ceux pour lesquels la page Conversation a déjà sonné
        if (nouveaux > 0 && nouveaux - consommerCreditConversation(nouveaux) > 0) bipNouveauMessage();
      }
      // Premier relevé = simple point de départ (pas de bip au chargement) ;
      // dans tous les cas, les bips « déjà sonnés » sont soldés à chaque relevé
      effacerCreditConversation();
    });
  }, [idMembre]);

  return null;
}
