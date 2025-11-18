"""Install AI assistant rules to configuration directories."""

import shutil
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Find project root by looking for common markers."""
    current = Path.cwd()
    markers = [".git", "pyproject.toml", "setup.py", "package.json"]

    # Search up to 5 levels
    for _ in range(5):
        if any((current / marker).exists() for marker in markers):
            return current
        if current.parent == current:  # Reached filesystem root
            break
        current = current.parent

    # Fallback to current directory
    return Path.cwd()


def install_rules(target_name: str, target_dir: Path | None = None) -> bool:
    """Install rules to AI assistant configuration directory.

    Args:
        target_name: Target AI assistant (amazonq, kiro, claude, cursor)
        target_dir: Optional custom target directory (default: auto-detect project root)

    Returns:
        True if successful, False otherwise
    """
    # Try multiple locations for rules directory
    possible_locations = [
        # Location 1: Standard installation - share/sqlobjects/rules
        Path(sys.prefix) / "share" / "sqlobjects" / "rules",
        # Location 2: Development mode - project root
        Path(__file__).parent.parent / "docs" / "rules",
    ]

    rules_dir = None
    for location in possible_locations:
        if location.exists() and list(location.glob("*.md")):
            rules_dir = location
            break

    if not rules_dir:
        print("Error: Rules directory not found in any of:", file=sys.stderr)
        for loc in possible_locations:
            print(f"  - {loc}", file=sys.stderr)
        return False

    # Determine base directory
    base_dir = target_dir if target_dir else find_project_root()

    # Target directory mapping (project-level)
    target_dirs = {
        "amazonq": base_dir / ".amazonq" / "rules" / "sqlobjects",
        "kiro": base_dir / ".kiro" / "rules" / "sqlobjects",
        "claude": base_dir / ".claude" / "rules" / "sqlobjects",
        "cursor": base_dir / ".cursor" / "rules" / "sqlobjects",
    }

    target_dir = target_dirs.get(target_name)
    if not target_dir:
        print(f"Error: Unknown target '{target_name}'", file=sys.stderr)
        print(f"Valid targets: {', '.join(target_dirs.keys())}", file=sys.stderr)
        return False

    if not rules_dir.exists():
        print(f"Error: Rules directory not found at {rules_dir}", file=sys.stderr)
        return False

    # Create target directory and copy files
    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        copied_count = 0
        for file in rules_dir.glob("*.md"):
            shutil.copy2(file, target_dir / file.name)
            copied_count += 1

        if copied_count > 0:
            actual_target = target_dirs[target_name]
            print(f"✓ Installed {copied_count} rule files to {actual_target}")
            return True
        else:
            print("Warning: No rule files found to install", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Error: Failed to install rules: {e}", file=sys.stderr)
        return False


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: sqlobjects-install-rules <target>")
        print()
        print("Install SQLObjects AI assistant rules to configuration directory.")
        print()
        print("Targets:")
        print("  amazonq  - Install to .amazonq/rules/sqlobjects/")
        print("  cursor   - Install to .cursor/rules/sqlobjects/")
        print("  claude   - Install to .claude/rules/sqlobjects/")
        print("  kiro     - Install to .kiro/rules/sqlobjects/")
        print()
        print("Examples:")
        print("  sqlobjects-install-rules amazonq")
        print("  sqlobjects-install-rules cursor")
        sys.exit(1)

    target = sys.argv[1].lower()
    success = install_rules(target)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
