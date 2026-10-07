"""Tools that build WRFrontiersDB-Data's `index/` from `current/`.

Standard library only, so any Python 3.11+ can run them without a virtualenv. The
functions are console-I/O free and return results; the Orchestrator's INDEX stage
(`src/stages/index.py`, on in every `--patch-day` run) calls them after each parse
and reports and publishes what they produce. `python -m wrfdb_data` runs them by
hand (see README.md).
"""
