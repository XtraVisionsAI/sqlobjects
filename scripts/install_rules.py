"""Install AI assistant rules to configuration directories."""

import shutil
import sys
from pathlib import Path


def install_rules(target_name: str) -> bool:
    """Install rules to AI assistant configuration directory.

    Args:
        target_name: Target AI assistant (amazonq, kiro, claude, cursor)

    Returns:
        True if successful, False otherwise
    """
    # Get rules directory from package installation
    try:
        # Find the package installation directory
        import sqlobjects

        package_root = Path(sqlobjects.__file__).parent.parent
        rules_dir = package_root / "docs" / "rules"
    except Exception as e:
        print(f"Error: Cannot locate sqlobjects package: {e}", file=sys.stderr)
        return False

    # Target directory mapping
    target_dirs = {
        "amazonq": Path.home() / ".amazonq" / "rules" / "sqlobjects",
        "kiro": Path.home() / ".kiro" / "rules" / "sqlobjects",
        "claude": Path.home() / ".claude" / "rules" / "sqlobjects",
        "cursor": Path.home() / ".cursor" / "rules" / "sqlobjects",
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
            print(f"✓ Installed {copied_count} rule files to {target_dir}")
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
        print("  amazonq  - Install to ~/.amazonq/rules/sqlobjects/")
        print("  cursor   - Install to ~/.cursor/rules/sqlobjects/")
        print("  claude   - Install to ~/.claude/rules/sqlobjects/")
        print("  kiro     - Install to ~/.kiro/rules/sqlobjects/")
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
