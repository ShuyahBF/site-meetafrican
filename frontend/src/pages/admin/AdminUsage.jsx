import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage, FOND } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Toast, { useToast } from "@/components/Toast";
import Patientez from "@/components/Patientez";

// ============================================================================
// ONGLET « USAGE » DU BACK-OFFICE (lot 47) — super-administrateur uniquement
// ============================================================================
// Historique de TOUTES les connexions des comptes, avec :
//   - une pastille de présence en tête de ligne (verte / orange / rouge),
//     rafraîchie toutes les 30 s par une requête de FOND (en-tête X-BA-Fond :
//     elle ne compte pas comme une activité de l'administrateur) ;
//   - date/heure (Ouagadougou), IP, compte (lien vers sa fiche), abonnement,
//     méthode et appareil, état de l'IP (autorisée / bloquée) ;
//   - les boutons Bloquer / Autoriser sur chaque ligne ;
// puis la liste « Blocages en cours », le journal des actions et le contact
// affiché sur la page « Accès momentanément suspendu ».
// Les règles côté serveur sont décrites dans backend/blocages_acces.py.
// ============================================================================

const RAFRAICHISSEMENT_PRESENCE_MS = 30_000;

// Couleurs des pastilles (mêmes règles que SAWALI)
const PASTILLES = {
  vert: { classe: "bg-emerald-500", texte: "Connecté et actif (activité dans les 5 dernières minutes)" },
  orange: { classe: "bg-amber-500", texte: "Connecté, sans activité depuis plus de 5 min (jusqu'à 10 min)" },
  rouge: { classe: "bg-red-500", texte: "Plus de 10 min sans activité, ou déconnecté" },
};

// Couleur du badge « état de l'abonnement »
const COULEURS_ABONNEMENT = {
  actif: "bg-emerald-50 text-emerald-700",
  grace: "bg-amber-50 text-amber-700",
  expire: "bg-red-50 text-red-600",
  aucun: "bg-slate-100 text-slate-500",
};

const ETATS_IP = {
  autorisee: { texte: "Autorisée", classe: "bg-emerald-50 text-emerald-700" },
  bloquee_tous: { texte: "Bloquée (tous les comptes)", classe: "bg-red-50 text-red-600" },
  bloquee_compte: { texte: "Bloquée (ce compte)", classe: "bg-red-50 text-red-600" },
};

// Date ISO -> « JJ/MM/AAAA HH:MM » à l'heure de Ouagadougou
function dateHeure(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const parties = Object.fromEntries(
    new Intl.DateTimeFormat("fr-FR", {
      timeZone: "Africa/Ouagadougou", day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(d).map((p) => [p.type, p.value]),
  );
  return `${parties.day}/${parties.month}/${parties.year} ${parties.hour}:${parties.minute}`;
}

// Pastille ronde de présence (avec info-bulle)
function Pastille({ presence }) {
  const p = PASTILLES[presence?.couleur] || PASTILLES.rouge;
  const titre = presence?.libelle || p.texte;
  return <span className={`inline-block h-3 w-3 rounded-full ${p.classe}`} title={titre} aria-label={titre} role="img" />;
}

const FILTRES_VIDES = { q: "", du: "", au: "", abonnement: "", etat: "" };

export default function AdminUsage() {
  const { user } = useAuth();
  const [toast, afficherToast] = useToast(3500);

  // --- Historique des connexions ---
  const [filtres, setFiltres] = useState(FILTRES_VIDES);   // saisie en cours
  const [appliques, setAppliques] = useState(FILTRES_VIDES); // filtres de la dernière recherche
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState({ items: [], total: 0, pages: 1 });
  const [chargement, setChargement] = useState(true);
  const [selection, setSelection] = useState(null);        // id de la ligne sélectionnée
  const [presence, setPresence] = useState({});            // sid -> pastille (rafraîchie)

  // --- Blocages, journal, contact ---
  const [blocages, setBlocages] = useState([]);
  const [journal, setJournal] = useState([]);
  const [contact, setContact] = useState({ email: "", whatsapp: "" });
  const [dialogue, setDialogue] = useState(null);          // ligne en cours de blocage

  const estSuperAdmin = user?.role === "admin";

  // Chargement de la page d'historique demandée. Le « Patientez… » est allumé par
  // les gestes qui déclenchent un chargement (recherche, changement de page) ;
  // les rechargements après une action restent silencieux.
  const chargerConnexions = useCallback(() => {
    const params = { page };
    Object.entries(appliques).forEach(([k, v]) => { if (v) params[k] = v; });
    return apiClient.get("/admin/usage/connexions", { params })
      .then((r) => { setDonnees(r.data); setPresence({}); })
      .catch((err) => afficherToast(extractErrorMessage(err, "Chargement impossible")))
      .finally(() => setChargement(false));
  }, [appliques, page, afficherToast]);

  // Blocages en cours + journal des actions
  const chargerBlocages = useCallback(() => {
    apiClient.get("/admin/usage/blocages").then((r) => setBlocages(r.data.blocages)).catch(() => {});
    apiClient.get("/admin/usage/journal").then((r) => setJournal(r.data.actions)).catch(() => {});
  }, []);

  useEffect(() => { if (estSuperAdmin) chargerConnexions(); }, [estSuperAdmin, chargerConnexions]);
  useEffect(() => {
    if (!estSuperAdmin) return;
    chargerBlocages();
    apiClient.get("/admin/usage/contact").then((r) => setContact(r.data)).catch(() => {});
  }, [estSuperAdmin, chargerBlocages]);

  // Rafraîchissement des pastilles toutes les 30 s (requête de FOND : pas une activité)
  const sidsRef = useRef("");
  useEffect(() => {
    sidsRef.current = donnees.items.map((l) => l.sid).filter(Boolean).join(",");
  }, [donnees]);
  useEffect(() => {
    if (!estSuperAdmin) return undefined;
    const minuteur = setInterval(() => {
      if (!sidsRef.current) return;
      apiClient.get("/admin/usage/presence", { params: { sids: sidsRef.current }, ...FOND })
        .then((r) => setPresence(r.data.presence)).catch(() => {});
    }, RAFRAICHISSEMENT_PRESENCE_MS);
    return () => clearInterval(minuteur);
  }, [estSuperAdmin]);

  // Action (bloquer, autoriser, lever) puis rechargement des listes
  const agir = async (appel, message) => {
    try {
      await appel();
      afficherToast(message);
      chargerBlocages();
      chargerConnexions();
      return true;
    } catch (err) {
      afficherToast(extractErrorMessage(err, "Action impossible"));
      return false;
    }
  };

  // Nouvelle recherche / autre page : « Patientez… » pendant le chargement
  const appliquer = (nouveaux) => {
    setChargement(true);
    setPage(1);
    setAppliques(nouveaux);
  };
  const allerPage = (n) => {
    setChargement(true);
    setPage(n);
  };

  const rechercher = (e) => {
    e.preventDefault();
    appliquer(filtres);
  };

  if (!estSuperAdmin) {
    return <p className="rounded-xl bg-white p-6 text-sm text-slate-500">Onglet réservé au super-administrateur.</p>;
  }

  return (
    <div>
      <Toast message={toast} />
      <Patientez actif={chargement} />

      <h1 className="text-2xl font-bold">Usage — historique des connexions</h1>
      <p className="mt-1 text-sm text-slate-500">
        Toutes les connexions des comptes (réussies et refusées), les plus récentes en haut.
        Conservation automatique : 180 jours. Heures de Ouagadougou.
      </p>

      {/* ---------------- Filtres ---------------- */}
      <form onSubmit={rechercher} className="mt-4 grid gap-2 sm:grid-cols-6">
        <input className="admin-input sm:col-span-2" placeholder="Compte (nom, e-mail, tél.) ou adresse IP"
               value={filtres.q} onChange={(e) => setFiltres({ ...filtres, q: e.target.value })} />
        <label className="flex flex-col text-xs text-slate-500">Du
          <input type="date" className="admin-input" value={filtres.du} onChange={(e) => setFiltres({ ...filtres, du: e.target.value })} />
        </label>
        <label className="flex flex-col text-xs text-slate-500">Au
          <input type="date" className="admin-input" value={filtres.au} onChange={(e) => setFiltres({ ...filtres, au: e.target.value })} />
        </label>
        <select className="admin-input" value={filtres.abonnement} onChange={(e) => setFiltres({ ...filtres, abonnement: e.target.value })}>
          <option value="">Abonnement : tous</option>
          <option value="actif">Actif</option>
          <option value="grace">Période de grâce</option>
          <option value="expire">Expiré</option>
          <option value="aucun">Aucun</option>
        </select>
        <select className="admin-input" value={filtres.etat} onChange={(e) => setFiltres({ ...filtres, etat: e.target.value })}>
          <option value="">Connexions : toutes</option>
          <option value="reussie">Réussies</option>
          <option value="refusee">Refusées</option>
        </select>
        <div className="flex gap-2 sm:col-span-6">
          <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Rechercher</button>
          <button type="button" className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold"
                  onClick={() => { setFiltres(FILTRES_VIDES); appliquer(FILTRES_VIDES); }}>
            Effacer les filtres
          </button>
        </div>
      </form>

      {/* ---------------- Légende des pastilles ---------------- */}
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 rounded-xl bg-white p-3 text-xs text-slate-600 ring-1 ring-slate-200">
        {Object.entries(PASTILLES).map(([cle, p]) => (
          <span key={cle} className="flex items-center gap-1.5">
            <span className={`inline-block h-3 w-3 rounded-full ${p.classe}`} aria-hidden="true" /> {p.texte}
          </span>
        ))}
        <span className="text-slate-400">Présence rafraîchie toutes les 30 s.</span>
      </div>

      {/* ---------------- Tableau des connexions ---------------- */}
      <p className="mt-4 text-sm text-slate-500">{donnees.total} connexion(s)</p>
      <div className="mt-2 overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2" aria-label="Présence" />
              <th className="px-3 py-2">Date / heure</th>
              <th className="px-3 py-2">Adresse IP</th>
              <th className="px-3 py-2">Compte</th>
              <th className="px-3 py-2">Abonnement</th>
              <th className="px-3 py-2">Méthode / appareil</th>
              <th className="px-3 py-2">État de l'IP</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!chargement && donnees.items.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-400">Aucune connexion.</td></tr>
            )}
            {donnees.items.map((l) => {
              const ipEtat = ETATS_IP[l.ip_etat] || ETATS_IP.autorisee;
              return (
                <tr key={l.id} aria-selected={selection === l.id} onClick={() => setSelection(l.id)} className="cursor-pointer align-top">
                  <td className="px-3 py-3"><Pastille presence={(l.sid && presence[l.sid]) || l.presence} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-600">
                    {dateHeure(l.date)}
                    {l.etat === "refusee" && (
                      <span className="mt-1 block w-fit rounded bg-red-50 px-1.5 text-[11px] font-semibold text-red-600">
                        Refusée ({l.motif === "compte" ? "compte bloqué" : "IP bloquée"})
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{l.ip || "—"}</td>
                  <td className="px-3 py-2">
                    {l.compte ? (
                      <Link to={`/admin/membres/${l.compte.id}`} onClick={(e) => e.stopPropagation()} className="font-semibold text-primary hover:underline">
                        {l.compte.nom || "Sans nom"}
                        {l.compte.super_admin && <span className="ml-1 rounded bg-slate-100 px-1 text-[10px] text-slate-500">SUPER-ADMIN</span>}
                        <span className="block text-xs font-normal text-slate-400">{l.compte.identifiant}</span>
                      </Link>
                    ) : (
                      <span className="text-slate-400">{l.identifiant || "Compte inconnu"}</span>
                    )}
                    {l.compte_bloque && <span className="mt-1 block w-fit rounded bg-red-50 px-1.5 text-[11px] font-semibold text-red-600">Compte bloqué</span>}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${COULEURS_ABONNEMENT[l.abonnement.statut] || COULEURS_ABONNEMENT.aucun}`}>
                      {l.abonnement.libelle}
                    </span>
                    {l.abonnement.formule && <span className="mt-1 block text-xs text-slate-500">{l.abonnement.formule}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {l.methode_libelle}
                    {l.appareil && <span className="block text-xs text-slate-400">{l.appareil}</span>}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-semibold ${ipEtat.classe}`}>{ipEtat.texte}</span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1">
                      <button type="button" className="rounded bg-red-600 px-2 py-1 text-xs font-semibold text-white"
                              onClick={(e) => { e.stopPropagation(); setDialogue(l); }}>
                        Bloquer…
                      </button>
                      {l.ip_etat !== "autorisee" && (
                        <button type="button" className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white"
                                onClick={(e) => { e.stopPropagation(); agir(() => apiClient.post("/admin/usage/autoriser", { type: "ip", ip: l.ip, user_id: l.compte?.id }), "Adresse IP autorisée."); }}>
                          Autoriser l'IP
                        </button>
                      )}
                      {l.compte_bloque && (
                        <button type="button" className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white"
                                onClick={(e) => { e.stopPropagation(); agir(() => apiClient.post("/admin/usage/autoriser", { type: "compte", user_id: l.compte?.id }), "Compte autorisé."); }}>
                          Autoriser le compte
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination : 50 lignes par page */}
      <div className="mt-3 flex items-center justify-between text-sm">
        <button disabled={page <= 1} onClick={() => allerPage(page - 1)} className="font-semibold text-slate-500 disabled:opacity-40">← Plus récentes</button>
        <span className="text-slate-500">Page {page} / {donnees.pages}</span>
        <button disabled={page >= donnees.pages} onClick={() => allerPage(page + 1)} className="font-semibold text-slate-500 disabled:opacity-40">Plus anciennes →</button>
      </div>

      {/* ---------------- Blocages en cours ---------------- */}
      <h2 className="mt-10 text-lg font-bold">Blocages en cours</h2>
      <div className="mt-2 overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Depuis le</th>
              <th className="px-3 py-2">Blocage</th>
              <th className="px-3 py-2">Compte</th>
              <th className="px-3 py-2">Nom / motif</th>
              <th className="px-3 py-2">Par</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {blocages.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-4 text-center text-slate-400">Aucun blocage en cours.</td></tr>
            )}
            {blocages.map((b) => (
              <tr key={b.id}>
                <td className="whitespace-nowrap px-3 py-2 text-slate-600">{dateHeure(b.cree_le)}</td>
                <td className="px-3 py-2">
                  {b.type === "compte" ? "Compte" : (
                    <><span className="font-mono text-xs">{b.ip}</span><span className="block text-xs text-slate-400">{b.portee === "tous" ? "pour tous les comptes" : "pour ce compte seulement"}</span></>
                  )}
                </td>
                <td className="px-3 py-2">
                  {b.user_id ? <Link to={`/admin/membres/${b.user_id}`} className="text-primary hover:underline">{b.compte_nom || b.compte_identifiant || "Compte"}</Link> : "—"}
                </td>
                <td className="px-3 py-2 text-slate-600">{[b.libelle, b.motif].filter(Boolean).join(" · ") || "—"}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{b.cree_par || "—"}</td>
                <td className="px-3 py-2 text-right">
                  <button type="button" className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white"
                          onClick={() => agir(() => apiClient.post(`/admin/usage/blocages/${b.id}/lever`), "Blocage levé : accès autorisé.")}>
                    Lever le blocage
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ---------------- Contact de la page de blocage ---------------- */}
      <h2 className="mt-10 text-lg font-bold">Contact affiché sur la page « Accès momentanément suspendu »</h2>
      <p className="mt-1 text-sm text-slate-500">
        Vide : le contact officiel des pages légales est affiché. Le visiteur bloqué ne voit aucun détail technique.
      </p>
      <form className="mt-2 grid gap-2 sm:grid-cols-3"
            onSubmit={(e) => { e.preventDefault(); agir(() => apiClient.put("/admin/usage/contact", contact).then((r) => setContact(r.data)), "Contact enregistré."); }}>
        <input className="admin-input" type="email" placeholder="E-mail de contact" value={contact.email}
               onChange={(e) => setContact({ ...contact, email: e.target.value })} />
        <input className="admin-input" placeholder="WhatsApp (ex. +226 70 00 00 00)" value={contact.whatsapp}
               onChange={(e) => setContact({ ...contact, whatsapp: e.target.value })} />
        <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Enregistrer</button>
      </form>

      {/* ---------------- Journal des actions ---------------- */}
      <h2 className="mt-10 text-lg font-bold">Journal des actions</h2>
      <div className="mt-2 overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Date / heure</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Détails</th>
              <th className="px-3 py-2">Par</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {journal.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-4 text-center text-slate-400">Aucune action.</td></tr>
            )}
            {journal.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap px-3 py-2 text-slate-600">{dateHeure(a.date)}</td>
                <td className="px-3 py-2 font-semibold">{a.action}</td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {[a.details?.ip && `IP ${a.details.ip}`, a.details?.libelle, a.details?.motif,
                    a.details?.sessions_fermees ? `${a.details.sessions_fermees} session(s) fermée(s)` : null]
                    .filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-500">{a.par || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialogue && (
        <DialogueBlocage ligne={dialogue} onFermer={() => setDialogue(null)}
                         onValider={(corps) => agir(() => apiClient.post("/admin/usage/blocages", corps), "Blocage enregistré : sessions concernées fermées.")
                           .then((ok) => ok && setDialogue(null))} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Fenêtre « Bloquer » : l'adresse IP (pour tous les comptes — coché par défaut,
// comme sur SAWALI — ou pour ce compte seulement) ou le compte lui-même.
// ----------------------------------------------------------------------------
function DialogueBlocage({ ligne, onFermer, onValider }) {
  const [cible, setCible] = useState(ligne.ip ? "ip" : "compte"); // « ip » ou « compte »
  const [tousComptes, setTousComptes] = useState(true);
  const [libelle, setLibelle] = useState("");
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const valider = async (e) => {
    e.preventDefault();
    setEnvoi(true);
    await onValider({
      type: cible, ip: cible === "ip" ? ligne.ip : null, user_id: ligne.compte?.id || null,
      tous_comptes: cible === "ip" ? tousComptes : false, libelle: libelle || null, motif: motif || null,
    });
    setEnvoi(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={(e) => e.target === e.currentTarget && onFermer()}>
      <form onSubmit={valider} className="w-full max-w-md space-y-3 rounded-xl bg-white p-5 text-sm shadow-2xl">
        <p className="text-lg font-bold">Bloquer l'accès</p>
        <p className="text-slate-500">
          {ligne.compte ? <>Compte <b>{ligne.compte.nom}</b> ({ligne.compte.identifiant})</> : "Compte inconnu"}
          {ligne.ip && <> · IP <span className="font-mono">{ligne.ip}</span></>}
        </p>

        {ligne.ip && (
          <label className="flex items-start gap-2">
            <input type="radio" name="cible" checked={cible === "ip"} onChange={() => setCible("ip")} className="mt-1" />
            <span>Bloquer l'adresse IP <span className="font-mono">{ligne.ip}</span></span>
          </label>
        )}
        {cible === "ip" && (
          <div className="ml-6 space-y-2">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={tousComptes} onChange={(e) => setTousComptes(e.target.checked)} disabled={!ligne.compte} />
              Pour tous les comptes
            </label>
            {!tousComptes && <p className="text-xs text-slate-500">Seul ce compte sera refusé depuis cette adresse.</p>}
            <input className="admin-input w-full" placeholder="Nom du site (facultatif, ex. Cybercafé du marché)" maxLength={120}
                   value={libelle} onChange={(e) => setLibelle(e.target.value)} />
          </div>
        )}
        {ligne.compte && (
          <label className="flex items-start gap-2">
            <input type="radio" name="cible" checked={cible === "compte"} onChange={() => setCible("compte")} className="mt-1" />
            <span>Bloquer le compte lui-même (depuis n'importe quelle adresse)</span>
          </label>
        )}
        <input className="admin-input w-full" placeholder="Motif interne (facultatif, jamais montré au membre)" maxLength={300}
               value={motif} onChange={(e) => setMotif(e.target.value)} />
        <p className="text-xs text-slate-500">
          Effet immédiat : les sessions concernées sont fermées et le visiteur voit la page « Accès momentanément suspendu ».
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={onFermer} className="flex-1 rounded-lg bg-slate-100 py-2 font-semibold">Annuler</button>
          <button disabled={envoi} className="flex-1 rounded-lg bg-red-600 py-2 font-semibold text-white disabled:opacity-50">
            {envoi ? "Patientez…" : "Bloquer"}
          </button>
        </div>
      </form>
    </div>
  );
}
