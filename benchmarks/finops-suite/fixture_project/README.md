# Fixture project (FinOps suite)

Temporary cwd target for `benchmarks/finops-suite` tasks.

Contains intentional tiny defects (`Helo` typo, off-by-one in `next_value`,
missing `clamp`) so tasks are realistic without depending on the VOLY monorepo.

Do not treat this tree as a product; runners copy it into a temp directory.
