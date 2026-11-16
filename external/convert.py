"""Build external weak-label test sets in the simulation dataset format.

    .venv/bin/python -m external.convert --source metrica --data-dir "$PWD/data"
    .venv/bin/python -m external.convert --source skillcorner --data-dir "$PWD/data"
    .venv/bin/python -m external.convert --source all --data-dir "$PWD/data"

Outputs go to ``outputs/simulation_sets/ext_<source>_<match>/``; the existing
``simulation.run_algorithm`` and ``simulation.evaluate`` read them without changes.
Raw data is read only under ``<data-dir>/external/``. Nothing here reads the BAR-ATH
answer, Smart Tagging, tactical files or the broadcast.
"""

import argparse
import os
import sys

from external import metrica, skillcorner


def _selected(path, requested):
    if not requested:
        return True
    wanted = {item.strip().lower() for item in requested.split(",") if item.strip()}
    basename = os.path.basename(os.path.abspath(path)).lower()
    aliases = {basename}
    if basename.startswith("sample_game_"):
        aliases.add("game_" + basename.rsplit("_", 1)[-1])
    return bool(aliases & wanted)


def _run_metrica(data_dir, requested, force):
    root = os.path.join(data_dir, "external", "metrica")
    if not os.path.isdir(root):
        raise SystemExit("Metrica data not found under {}".format(root))
    paths = [path for path in metrica.discover_games(root) if _selected(path, requested)]
    if not paths:
        raise SystemExit("no Metrica game matched --match {!r}".format(requested))
    for path in paths:
        print("converting {}".format(os.path.relpath(path, data_dir)))
        metrica.convert_game(path, force=force)


def _run_skillcorner(data_dir, requested, force):
    root = os.path.join(data_dir, "external", "skillcorner")
    if not os.path.isdir(root):
        raise SystemExit("SkillCorner data not found under {}".format(root))
    paths = [path for path in skillcorner.discover_matches(root) if _selected(path, requested)]
    if not paths:
        raise SystemExit("no SkillCorner match matched --match {!r}".format(requested))
    for path in paths:
        print("converting {}".format(os.path.relpath(path, data_dir)))
        skillcorner.convert_match(path, force=force)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, choices=("metrica", "skillcorner", "all"))
    parser.add_argument("--data-dir", default="data",
                        help="match asset root containing external/ (default: data)")
    parser.add_argument("--match", help="optional comma-separated match names or ids")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing ext_<source>_<match> dataset")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    if args.source in ("metrica", "all"):
        _run_metrica(data_dir, args.match, args.force)
    if args.source in ("skillcorner", "all"):
        _run_skillcorner(data_dir, args.match, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
