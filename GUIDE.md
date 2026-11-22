# Reviewing dataset splits

Use stable sample IDs, group identifiers, one class label per sample and the current split. A group might be a participant, recording session, household or source document. Choose it according to the leakage mechanism. Target fractions must sum to one. Keep the source table immutable and apply the exported manifest in the training pipeline.

The audit freezes groups already confined to one split. It visits leaking groups from largest to smallest and proposes whole-group destinations. The recommendation minimizes the incremental weighted class-count error for that step. Rare classes retain weight, and ties favor keeping more existing assignments. Alternative destinations remain reviewable. Recommendations are greedy, so they cannot guarantee perfect stratification.

The manifest retains every sample, original split and assigned split. An unresolved leaking group goes entirely to quarantine. Conflicting approvals are rejected. A class-by-split CSV compares approved assignments against the intended counts, and a JSON list names quarantined groups. Similar images or people represented by different group IDs still need a separate duplicate or identity audit.
