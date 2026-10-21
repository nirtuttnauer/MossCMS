# Pre-load setup stopped

The 100k setup exposed repeated deletes/scans during backfill of a newly created or truncated projection. The controller was interrupted before the timed HTTP workload began and cleaned up its disposable fixtures. Empty-projection backfills now skip those deletes; repair of existing projections retains them. This incomplete run is excluded from the README graphs.
