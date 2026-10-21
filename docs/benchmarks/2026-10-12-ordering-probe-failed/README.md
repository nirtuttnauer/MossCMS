# Incomplete benchmark probe

The 60-second HTTP workload and migration completed, but the new sequential ordering probe mistakenly collected HTTP response objects instead of elapsed milliseconds. Verification then failed before backup/restore. The manifest is incomplete and this sample is excluded from the README graph. The timing collection was corrected and the complete run repeated in `../2026-10-12-ordering`. Temporary containers and volumes were cleaned up.
