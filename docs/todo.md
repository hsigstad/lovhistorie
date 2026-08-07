# Todo

## Henrik — manual (ground truth for the eval)

- [ ] **Download Lovdata Pro historical versions** for the ground-truth eval set.
  Spec: `docs/ground_truth.md`. Save each as **HTML** ("Historiske versjoner" →
  date → save-as-HTML). Drop them in the repo root (I'll file + parse them) or
  directly into `data/ground_truth/<datokode>/<YYYY-MM-DD>.html`.
  - Priority 8: aksjeloven `1997-06-13-44` (started — 2003 done), rettsgebyrloven
    `1982-12-17-86`, avtaleloven `1918-05-31-4`, oreigningslova `1959-10-23-3`,
    kjøpsloven `1988-05-13-27`, verdipapirhandelloven `2007-06-29-75`,
    mesterbrevloven `1986-06-20-35`, tjenesteloven `2009-06-19-103` (negative control).
  - Then: tinglysingsloven `1935-06-07-2`, utleveringsloven `1975-06-13-39`,
    Statens pensjonskasse `1949-07-28-26`, bioteknologiloven `2003-12-05-100`,
    utlendingsloven `2008-05-15-35`, Oppgaveregisteret `1997-06-06-35`.
  - ~3–5 dates per law, spread across its life, bracketing major amendments.
  - This unblocks the point-in-time metric → autonomous work via the `goal` skill.
