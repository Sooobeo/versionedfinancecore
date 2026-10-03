from __future__ import annotations

import argparse
import csv
from pathlib import Path

from versioned_finance_core.orchestration.core_build import build_core
from versioned_finance_core.orchestration.release import (
    case_release_readiness_issues,
    publish_release,
    stage_release,
    write_manifest,
)
from versioned_finance_core.orchestration.scaffold import initialize_case, validate_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vfc", description="Versioned Finance Core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-case", help="Create a case from cases/_template")
    init_parser.add_argument("case_id")
    init_parser.add_argument("--cases-dir", type=Path, default=Path("cases"))
    init_parser.add_argument("--template", type=Path, default=Path("cases/_template"))

    validate_parser = subparsers.add_parser(
        "validate-case", help="Validate case structure and optional release evidence/gates"
    )
    validate_parser.add_argument("case_dir", type=Path)
    validate_parser.add_argument("--release-ready", action="store_true")

    manifest_parser = subparsers.add_parser("build-manifest", help="Hash a case snapshot")
    manifest_parser.add_argument("case_dir", type=Path)
    manifest_parser.add_argument("--output", type=Path)

    core_parser = subparsers.add_parser("build-core", help="Build the D0 core cash slice")
    core_parser.add_argument("case_dir", type=Path)
    core_parser.add_argument("--build-root", type=Path, default=Path("build"))

    case_parser = subparsers.add_parser(
        "build-case", help="Reproduce a declared offline case recipe and stage a review bundle"
    )
    case_parser.add_argument("case_dir", type=Path)
    case_parser.add_argument("--build-root", type=Path, default=Path("build"))

    verify_parser = subparsers.add_parser(
        "verify-build", help="Verify review bundle hashes and controls without publishing"
    )
    verify_parser.add_argument("stage_dir", type=Path)

    reproduce_parser = subparsers.add_parser(
        "reproduce-case", help="Run two fresh builds and record automated handover checks"
    )
    reproduce_parser.add_argument("case_dir", type=Path)
    reproduce_parser.add_argument("--output-dir", type=Path, required=True)

    handover_parser = subparsers.add_parser(
        "verify-reproduction", help="Verify a two-build handover bundle without human sign-off"
    )
    handover_parser.add_argument("bundle_dir", type=Path)

    stage_parser = subparsers.add_parser("stage-release", help="Stage a withheld case snapshot")
    stage_parser.add_argument("case_dir", type=Path)
    stage_parser.add_argument("--stage-root", type=Path, default=Path("build"))
    stage_parser.add_argument("--core-build", type=Path, required=True)
    stage_parser.add_argument("--reproduction-command", required=True)

    publish_parser = subparsers.add_parser(
        "publish-release", help="Publish a stage only after every gate passes"
    )
    publish_parser.add_argument("stage_dir", type=Path)
    publish_parser.add_argument("--releases-root", type=Path, default=Path("releases"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "init-case":
            destination = initialize_case(args.case_id, args.cases_dir, args.template)
            print(f"Created case scaffold: {destination}")
            return 0

        if args.command == "validate-case":
            errors, warnings = validate_case(args.case_dir, args.release_ready)
            if args.release_ready and not errors:
                errors.extend(case_release_readiness_issues(args.case_dir))
            for warning in warnings:
                print(f"WARNING: {warning}")
            for error in errors:
                print(f"ERROR: {error}")
            if errors:
                return 1
            if args.release_ready:
                print("Case structure, source eligibility, and release gates are valid.")
                print("Output and reproduction controls are checked at staging and publication.")
            else:
                print("Case structure is valid; evidence lineage is valid.")
            return 0

        if args.command == "build-manifest":
            target = write_manifest(args.case_dir, args.output)
            print(f"Wrote release manifest: {target}")
            return 0

        if args.command == "build-core":
            target = build_core(args.case_dir, args.build_root)
            print(f"Built core staging: {target}")
            return 0

        if args.command == "build-case":
            from versioned_finance_core.orchestration.case_build import build_case

            target = build_case(args.case_dir, args.build_root)
            print(f"Built case review: {target}")
            print("Reproduction succeeded; publication remains WITHHELD.")
            print(f"Review memo: {target / 'outputs/review_memo.md'}")
            return 0

        if args.command == "verify-build":
            from versioned_finance_core.orchestration.case_build import verify_case_build

            result = verify_case_build(args.stage_dir)
            print(f"Review build integrity: {result['integrity_state']}")
            print(f"Publication: {result['publication_state']}; release ready: {result['release_ready']}")
            print(f"Output hash: {result['output_hash']}")
            return 0

        if args.command == "reproduce-case":
            from versioned_finance_core.orchestration.reproduction import reproduce_case

            target = reproduce_case(args.case_dir, args.output_dir)
            print(f"Automated reproduction handover: {target}")
            print("Two fresh builds matched; independent human review was not performed.")
            print("Publication remains WITHHELD; source case gates were not changed.")
            return 0

        if args.command == "verify-reproduction":
            from versioned_finance_core.orchestration.reproduction import verify_reproduction

            result = verify_reproduction(args.bundle_dir)
            print(f"Reproduction bundle integrity: {result['integrity_state']}")
            print(f"Automated reproduction: {result['automated_reproduction_state']}")
            print(f"Human review: {result['human_review_state']}; publication: WITHHELD")
            print(f"Output ID: {result['output_id']}")
            return 0

        if args.command == "stage-release":
            external = {
                f"outputs/{name}": args.core_build / name
                for name in (
                    "normalized_actuals.csv", "core_outputs.json",
                    "memo_fields.json", "build_metadata.json",
                )
            }
            target = stage_release(
                args.case_dir,
                args.stage_root,
                external_outputs=external,
                output_paths=(
                    "outputs/normalized_actuals.csv",
                    "outputs/core_outputs.json",
                    "outputs/memo_fields.json",
                    "outputs/build_metadata.json",
                ),
                memo_paths=("outputs/memo_fields.json",),
                reproduction_command=args.reproduction_command,
            )
            print(f"Staged release snapshot: {target}")
            return 0

        if args.command == "publish-release":
            target = publish_release(args.stage_dir, args.releases_root)
            print(f"Published immutable release: {target}")
            return 0
    except (FileExistsError, FileNotFoundError, ValueError, TypeError, KeyError, csv.Error) as exc:
        print(f"ERROR: {exc}")
        return 2

    return 2

