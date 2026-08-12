# Data backups (Dropbox)

Large/encumbered data is gitignored; this logs Dropbox backups of it (for restore on
other machines, e.g. educloud). Archives are built with `tar czf` from `data/`; restore
with `tar xzf <archive> -C data/`.
