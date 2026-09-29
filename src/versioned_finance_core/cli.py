from __future__ import annotations

import argparse
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
                print("Case structure is valid.")
            return 0

        if args.command == "build-manifest":
            target = write_manifest(args.case_dir, args.output)
            print(f"Wrote release manifest: {target}")
            return 0

        if args.command == "build-core":
            target = build_core(args.case_dir, args.build_root)
            print(f"Built core staging: {target}")
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
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    return 2

