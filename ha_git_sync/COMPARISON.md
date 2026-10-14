# Design notes

Git runs in an isolated checkout, and every write starts from a reviewed commit. This keeps Git out of the active configuration directory and allows explicit file scope, backup, validation and journaled recovery.

Push uses a lease against the previewed remote commit. Import checks the local snapshot against the preview before applying. These detect changes after previewing; they do not perform a three-way merge or resolve independently edited content.

Files missing from an import branch are preserved by default. Deletion is explicitly enabled before previewing and covered by backup/recovery. Unselected GitHub files remain untouched. Diffs are bounded and hidden when secret scanning flags their content.

Possible future improvements include three-way comparison, status sensors, domain-specific reload actions and a pull-request link after push. These need dedicated behavior and tests before adoption.
