#!/usr/bin/env python3
"""
UI Audit Pro — Platform Installer

Install ui-audit-pro as a skill into various AI coding assistants.

Usage:
    python3 scripts/install.py --platform <platform>    # Install to specific platform
    python3 scripts/install.py --all                     # Install to all detected platforms
    python3 scripts/install.py --detect                  # Detect installed platforms
    python3 scripts/install.py --uninstall --platform <platform>  # Uninstall from platform

Platforms:
    claude-code, codex, cursor, gemini-cli, kiro, copilot

Options:
    --global, -g        Install to user-level directory (global across projects)
    --symlink           Use symlinks instead of copying files
    --dry-run           Show what would be done without making changes
    --verbose, -v       Show detailed output
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Optional


# ─── Platform Configuration ───────────────────────────────────────────────────

PLATFORMS = {
    "claude-code": {
        "name": "Claude Code",
        "project_dir": ".claude/skills",
        "user_dir": "~/.claude/skills",
        "indicators": [".claude"],
        "user_indicators": ["~/.claude"],
    },
    "codex": {
        "name": "OpenAI Codex",
        "project_dir": ".agents/skills",
        "user_dir": "~/.agents/skills",
        "indicators": [".agents", ".codex"],
        "user_indicators": ["~/.agents", "~/.codex"],
    },
    "cursor": {
        "name": "Cursor",
        "project_dir": ".cursor/skills",
        "user_dir": "~/.cursor/skills",
        "indicators": [".cursor", ".agents"],
        "user_indicators": ["~/.cursor", "~/.agents"],
    },
    "gemini-cli": {
        "name": "Gemini CLI",
        "project_dir": ".gemini/skills",
        "user_dir": "~/.gemini/skills",
        "indicators": [".gemini", ".agents"],
        "user_indicators": ["~/.gemini", "~/.agents"],
    },
    "kiro": {
        "name": "Kiro",
        "project_dir": ".kiro/skills",
        "user_dir": "~/.kiro/skills",
        "indicators": [".kiro", ".agents"],
        "user_indicators": ["~/.kiro", "~/.agents"],
    },
    "copilot": {
        "name": "GitHub Copilot",
        "project_dir": ".github/instructions",
        "user_dir": "~/.copilot/instructions",
        "indicators": [".github"],
        "user_indicators": ["~/.copilot"],
        "is.instructions": True,  # Copilot uses .instructions.md files
    },
}

SKILL_NAME = "ui-audit-pro"

# Files and directories to copy with the skill
SKILL_CONTENT = [
    "SKILL.md",
    "requirements.txt",
    "scripts/",
    "references/",
]


# ─── Utility Functions ────────────────────────────────────────────────────────

def expand_path(path: str) -> Path:
    """Expand ~ and resolve to absolute path."""
    return Path(os.path.expanduser(path)).resolve()


def get_skill_source_dir() -> Path:
    """Get the directory where ui-audit-pro is installed."""
    # scripts/install.py -> project root
    return Path(__file__).parent.parent.resolve()


def detect_platforms(cwd: Optional[Path] = None) -> list[str]:
    """Detect which AI coding platforms are present in the current directory."""
    if cwd is None:
        cwd = Path.cwd()

    detected = []
    for platform_key, config in PLATFORMS.items():
        # Check project-level indicators
        for indicator in config["indicators"]:
            indicator_path = cwd / indicator
            if indicator_path.exists():
                detected.append(platform_key)
                break

    return detected


def detect_user_platforms() -> list[str]:
    """Detect which AI coding platforms have user-level configs."""
    detected = []
    for platform_key, config in PLATFORMS.items():
        for indicator in config["user_indicators"]:
            indicator_path = expand_path(indicator)
            if indicator_path.exists():
                detected.append(platform_key)
                break

    return detected


def get_target_dir(platform: str, global_install: bool) -> Path:
    """Get the target directory for a platform installation."""
    config = PLATFORMS[platform]
    if global_install:
        return expand_path(config["user_dir"])
    else:
        return Path.cwd() / config["project_dir"]


def skill_already_installed(target_dir: Path, platform: str) -> bool:
    """Check if the skill is already installed at the target location."""
    if config_is_instructions(platform):
        return (target_dir / f"{SKILL_NAME}.instructions.md").exists()
    skill_dir = target_dir / SKILL_NAME
    return skill_dir.exists() and (skill_dir / "SKILL.md").exists()


def config_is_instructions(platform: str) -> bool:
    """Check if the platform uses .instructions.md format."""
    return PLATFORMS[platform].get("is.instructions", False)


# ─── Install Logic ────────────────────────────────────────────────────────────

def copy_skill_content(source: Path, target: Path, verbose: bool = False):
    """Copy skill files from source to target directory."""
    target.mkdir(parents=True, exist_ok=True)

    for item in SKILL_CONTENT:
        src_path = source / item
        dst_path = target / item

        if not src_path.exists():
            if verbose:
                print(f"  [skip] {item} (not found)")
            continue

        if src_path.is_dir():
            if verbose:
                print(f"  [copy] {item}/")
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        else:
            if verbose:
                print(f"  [copy] {item}")
            shutil.copy2(src_path, dst_path)


def symlink_skill_content(source: Path, target: Path, verbose: bool = False):
    """Create symlinks from source to target directory."""
    target.mkdir(parents=True, exist_ok=True)

    for item in SKILL_CONTENT:
        src_path = source / item
        dst_path = target / item

        if not src_path.exists():
            if verbose:
                print(f"  [skip] {item} (not found)")
            continue

        # Remove existing if present
        if dst_path.exists() or dst_path.is_symlink():
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()

        if verbose:
            print(f"  [link] {item} -> {src_path}")
        os.symlink(src_path, dst_path)


def generate_copilot_instructions(source: Path, target: Path, verbose: bool = False):
    """Generate a .instructions.md file for GitHub Copilot."""
    target.mkdir(parents=True, exist_ok=True)

    skill_md = source / "SKILL.md"
    if not skill_md.exists():
        print("  [error] SKILL.md not found")
        return

    instructions_content = skill_md.read_text()

    # Add Copilot-specific frontmatter if not present
    if instructions_content.startswith("---"):
        # Already has frontmatter, add applyTo
        lines = instructions_content.split("\n")
        # Insert applyTo after the first ---
        lines.insert(1, 'applyTo: "**"')
        instructions_content = "\n".join(lines)
    else:
        instructions_content = f'---\napplyTo: "**"\n---\n\n{instructions_content}'

    output_path = target / f"{SKILL_NAME}.instructions.md"
    if verbose:
        print(f"  [write] {output_path.name}")
    output_path.write_text(instructions_content)


def install_skill(
    platform: str,
    global_install: bool = False,
    use_symlink: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Install ui-audit-pro to a specific platform."""
    config = PLATFORMS[platform]
    source = get_skill_source_dir()
    target = get_target_dir(platform, global_install)

    scope = "global" if global_install else "project"
    print(f"\n{'─' * 50}")
    print(f"Installing to {config['name']} ({scope})")
    print(f"  Source: {source}")
    print(f"  Target: {target}")

    if skill_already_installed(target, platform):
        print(f"  [!] Skill already installed at {target}")
        print(f"      Use --uninstall first to reinstall")
        return False

    if dry_run:
        print(f"\n  [dry-run] Would install to: {target}")
        for item in SKILL_CONTENT:
            src_path = source / item
            if src_path.exists():
                print(f"  [dry-run]   {item}")
        return True

    # Install based on platform type
    if config_is_instructions(platform):
        generate_copilot_instructions(source, target, verbose)
    elif use_symlink:
        symlink_skill_content(source, target, verbose)
    else:
        copy_skill_content(source, target, verbose)

    print(f"  [ok] Installed to {target}")
    return True


# ─── Uninstall Logic ──────────────────────────────────────────────────────────

def uninstall_skill(
    platform: str,
    global_install: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Uninstall ui-audit-pro from a specific platform."""
    config = PLATFORMS[platform]
    target = get_target_dir(platform, global_install)

    scope = "global" if global_install else "project"
    print(f"\n{'─' * 50}")
    print(f"Uninstalling from {config['name']} ({scope})")

    if config_is_instructions(platform):
        target_file = target / f"{SKILL_NAME}.instructions.md"
        if not target_file.exists():
            print(f"  [!] Skill not installed at {target_file}")
            return False

        if dry_run:
            print(f"  [dry-run] Would remove: {target_file}")
            return True

        if verbose:
            print(f"  [remove] {target_file}")
        target_file.unlink()
        print(f"  [ok] Uninstalled from {target}")
        return True
    else:
        skill_dir = target / SKILL_NAME
        if not skill_dir.exists():
            print(f"  [!] Skill not installed at {skill_dir}")
            return False

        if dry_run:
            print(f"  [dry-run] Would remove: {skill_dir}")
            return True

        if verbose:
            print(f"  [remove] {skill_dir}")
        shutil.rmtree(skill_dir)
        print(f"  [ok] Uninstalled from {target}")
        return True


# ─── Detect Command ───────────────────────────────────────────────────────────

def show_detection():
    """Show detected platforms."""
    print("\nDetecting installed AI coding platforms...\n")

    project_platforms = detect_platforms()
    user_platforms = detect_user_platforms()

    if project_platforms:
        print("  Project-level (current directory):")
        for p in project_platforms:
            config = PLATFORMS[p]
            print(f"    ✓ {config['name']} ({config['project_dir']})")
    else:
        print("  Project-level: None detected")

    if user_platforms:
        print("\n  User-level (global):")
        for p in user_platforms:
            config = PLATFORMS[p]
            print(f"    ✓ {config['name']} ({config['user_dir']})")
    else:
        print("\n  User-level: None detected")

    if not project_platforms and not user_platforms:
        print("\n  No platforms detected. You can still install manually:")
        print(f"    python3 scripts/install.py --platform <platform>")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="UI Audit Pro — Platform Installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --detect                      # Detect installed platforms
  %(prog)s --platform claude-code        # Install to Claude Code
  %(prog)s --platform codex --global     # Install globally for Codex
  %(prog)s --all                         # Install to all detected platforms
  %(prog)s --all --global                # Install globally to all platforms
  %(prog)s --uninstall --platform cursor # Uninstall from Cursor
  %(prog)s --platform kiro --dry-run     # Preview installation
        """,
    )

    parser.add_argument(
        "--platform",
        "-p",
        choices=list(PLATFORMS.keys()),
        help="Target platform to install/uninstall",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install to all detected platforms",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Detect installed AI coding platforms",
    )
    parser.add_argument(
        "--global",
        "-g",
        dest="global_install",
        action="store_true",
        help="Install to user-level directory (global across projects)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall the skill from the specified platform(s)",
    )
    parser.add_argument(
        "--symlink",
        action="store_true",
        help="Use symlinks instead of copying files (single source of truth)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    # Handle --detect
    if args.detect:
        show_detection()
        return 0

    # Determine target platforms
    platforms_to_install = []

    if args.all:
        platforms_to_install = detect_platforms()
        if not platforms_to_install:
            print("No platforms detected in current directory.")
            print("Use --platform <name> to specify a platform manually.")
            return 1
        print(f"Detected platforms: {', '.join(platforms_to_install)}")
    elif args.platform:
        platforms_to_install = [args.platform]
    else:
        parser.print_help()
        return 1

    # Execute install or uninstall
    success_count = 0
    total = len(platforms_to_install)

    if args.uninstall:
        for platform in platforms_to_install:
            if uninstall_skill(
                platform,
                global_install=args.global_install,
                dry_run=args.dry_run,
                verbose=args.verbose,
            ):
                success_count += 1
    else:
        for platform in platforms_to_install:
            if install_skill(
                platform,
                global_install=args.global_install,
                use_symlink=args.symlink,
                dry_run=args.dry_run,
                verbose=args.verbose,
            ):
                success_count += 1

    # Summary
    action = "Uninstalled" if args.uninstall else "Installed"
    print(f"\n{'═' * 50}")
    print(f"{action} {success_count}/{total} platform(s)")
    print(f"{'═' * 50}")

    if not args.uninstall and success_count > 0 and not args.dry_run:
        print("\nNext steps:")
        print("  1. Restart your AI coding assistant")
        print("  2. Ask it to run a UI audit:")
        print('     "Audit this codebase for UI/UX consistency issues"')
        print(f"\n  Or run directly:")
        print(f"    python3 scripts/audit.py full --codebase /path/to/app --url http://localhost:3000")

    return 0 if success_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
