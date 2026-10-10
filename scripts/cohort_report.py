#!/usr/bin/env python3
"""Print the measured results of the active cohort build.

With no arguments this prints the full report. The two status flags rewrite
and verify the generated block in CLAUDE.md's ``## Status`` section, which is
where those figures used to be transcribed by hand and drift:

    python3 scripts/cohort_report.py                 # the full report
    python3 scripts/cohort_report.py --write-status  # refresh CLAUDE.md
    python3 scripts/cohort_report.py --check-status  # exit 1 if it is stale
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import report, status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-status", action="store_true",
        help="rewrite the generated block in CLAUDE.md's ## Status section "
             "from the active database, the exported payload and the test "
             "suites. Everything outside the markers is left byte-identical.")
    mode.add_argument(
        "--check-status", action="store_true",
        help="exit non-zero, with a diff, when that block disagrees with what "
             "those sources say now.")
    parser.add_argument(
        "--db", type=pathlib.Path, default=None,
        help="cohort database to read instead of the active db/cohort1.db")
    args = parser.parse_args(argv)

    try:
        if args.write_status:
            return status.write(db_path=args.db)
        if args.check_status:
            return status.check(db_path=args.db)
    except status.StatusError as exc:
        print(f"cohort_report: {exc}", file=sys.stderr)
        return 2
    return report.run(args.db)


if __name__ == "__main__":
    sys.exit(main())
