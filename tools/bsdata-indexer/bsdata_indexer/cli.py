from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import faction_map
from .build import BSDATA_ORG, CATALOGUE_REPO, MFM_REPO, build_faction, build_library_index, build_profile_index, emit
from .enrichment import pipeline as enrichment_pipeline
from .enrichment import tier2
from .fetch import RepoCache
from .util import slugify

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = HERE / "cache"
DEFAULT_OUTPUT_DIR = HERE / "output"


def _catalogue_faction_stems(catalogue_cache: RepoCache) -> list[str]:
    names = catalogue_cache.list_files()
    return [n[:-5] for n in names if n.endswith(".json")]


def _mfm_slugs(mfm_cache: RepoCache) -> set[str]:
    names = mfm_cache.list_files(path="data")
    return {n[:-5] for n in names if n.endswith(".yaml") and n != "meta.yaml"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build UnitDefinition JSON from BSData.")
    parser.add_argument(
        "--faction",
        action="append",
        help='Catalogue file stem, e.g. "Aeldari - Craftworlds". Repeatable.',
    )
    parser.add_argument("--all", action="store_true", help="Build every faction with a known/derivable MFM mapping.")
    parser.add_argument("--force-refetch", action="store_true", help="Ignore cache, re-download everything.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--enrich",
        action="store_true",
        help=(
            "Also run synergy enrichment (SPEC.md) on each built faction's abilities. "
            "Tier 1 is free/local; anything it can't resolve is sent to the Anthropic Batches "
            "API (Tier 2) -- opt-in because that costs money and needs API credentials."
        ),
    )
    parser.add_argument(
        "--model",
        default=tier2.DEFAULT_MODEL,
        help=f"Model for Tier 2 enrichment calls (default: {tier2.DEFAULT_MODEL}). Only used with --enrich.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    if not args.faction and not args.all:
        parser.error("pass --faction NAME (repeatable) or --all")

    catalogue_cache = RepoCache(args.cache_dir, BSDATA_ORG, CATALOGUE_REPO)
    mfm_cache = RepoCache(args.cache_dir, BSDATA_ORG, MFM_REPO)
    catalogue_cache.refresh(force=args.force_refetch)
    mfm_cache.refresh(force=args.force_refetch)

    available_slugs = _mfm_slugs(mfm_cache)
    library_index = build_library_index(catalogue_cache)
    profile_index = build_profile_index(catalogue_cache)

    enrich_client = None
    if args.enrich:
        import anthropic  # optional dependency -- only imported when --enrich is actually used

        enrich_client = anthropic.Anthropic()

    if args.all:
        all_stems = _catalogue_faction_stems(catalogue_cache)
        stems = [s for s in all_stems if s not in faction_map.NOT_APPLICABLE]
    else:
        stems = args.faction

    exit_code = 0
    for stem in stems:
        try:
            report = build_faction(
                stem,
                catalogue_cache,
                library_index,
                profile_index,
                mfm_cache,
                available_mfm_slugs=available_slugs,
            )
        except Exception as exc:  # noqa: BLE001 - per-faction isolation for a batch CLI run
            logger.error("%s: FAILED - %s", stem, exc)
            exit_code = 1
            continue
        out_path = emit(report, args.output_dir)
        unmatched = sum(1 for u in report.units if not u.mfm_matched)
        logger.info(
            "%s -> %s (%d units, %d unmatched against MFM, mfm_slug=%s%s, %d unresolved entryLinks)",
            stem,
            out_path,
            len(report.units),
            unmatched,
            report.mfm_slug,
            " [guessed]" if report.mfm_slug_guessed else "",
            len(report.unresolved_entrylinks),
        )
        if report.mfm_slug is None:
            logger.warning("%s: no MFM slug mapped -- every unit emitted with mfm_matched=False", stem)

        if args.enrich:
            synergies_path = args.output_dir / f"{slugify(stem)}-synergies.json"
            previous = enrichment_pipeline.load_previous(synergies_path)
            candidates = enrichment_pipeline.enrich_faction(
                report.units, previous, client=enrich_client, model=args.model
            )
            out_synergies_path = enrichment_pipeline.emit(stem, candidates, args.output_dir)
            tier1_count = sum(1 for c in candidates if c.tier == "tier1")
            tier2_count = sum(1 for c in candidates if c.tier == "tier2")
            logger.info(
                "%s -> %s (%d synergy candidates: %d tier1, %d tier2)",
                stem,
                out_synergies_path,
                len(candidates),
                tier1_count,
                tier2_count,
            )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
