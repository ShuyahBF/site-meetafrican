// Encapsule une maquette VIDAL (fichier HTML autonome) dans un <iframe> isolé.
// Le contenu brut (importé via `?raw`) n'a ni <!doctype>/<html>/<body> propres
// (habitude des artefacts Claude, qui les enveloppent à la publication) : on
// reconstruit ici un document HTML complet et minimal avant de l'injecter en
// srcDoc, sans attribut "sandbox" pour ne pas brider les scripts/fetches des
// maquettes (QR code, Google Fonts, etc.).
export default function SecureFrame({ html, title }) {
  const doc = `<!doctype html><html lang="fr"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head><body style="margin:0">${html}<style>
    /* La maquette Posologie a un fond transparent pensé pour un futur hébergement
       dans la page d'un site hôte. Ici, dans la zone /secure, il n'y a pas de tel
       site hôte : on retombe donc sur le fond propre de la maquette (var(--bg),
       déjà correct en clair comme en sombre) plutôt que de laisser transparaître
       le gris de cette coquille de test. Sans effet sur les maquettes qui ont déjà
       leur propre fond opaque. */
    body{ background:var(--bg) !important; }
  </style></body></html>`;

  return (
    <iframe
      title={title}
      srcDoc={doc}
      style={{ width: "100%", height: "100%", border: "none", display: "block" }}
    />
  );
}
