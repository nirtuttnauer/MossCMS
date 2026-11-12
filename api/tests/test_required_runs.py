import required_runs


def test_committed_deselection_matches_markers_and_covers_every_test():
    problems = required_runs.check_manifest(required_runs.collect_full_suite())
    assert not problems, "\n".join(problems)
