import os
import re
import shutil
import sys
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.develop import develop
from setuptools.command.install import install


class PostInstallCommand(install):
    """Post-installation for installation mode."""

    user_options = install.user_options + [
        ("extras=", None, "Extras to install (comma-separated)"),
    ]

    def __init__(self, dist: Distribution):
        super().__init__(dist)
        self.extras: str | None = None

    def initialize_options(self):
        install.initialize_options(self)
        self.extras = None

    def run(self):
        install.run(self)
        self._post_install()

    def _post_install(self):
        """执行安装后的 rules 复制"""
        extras_to_install = set()

        # 方法1: 从环境变量获取
        env_extras = os.environ.get("SQLOBJECTS_INSTALL_EXTRAS", "")
        if env_extras:
            extras_to_install.update(e.strip() for e in env_extras.split(","))

        # 方法2: 从命令行参数检测
        for arg in sys.argv:
            # 匹配 sqlobjects[amazonq] 或 .[amazonq] 格式
            match = re.search(r"\[([^\]]+)\]", arg)
            if match:
                extras_str = match.group(1)
                extras_to_install.update(e.strip() for e in extras_str.split(","))

        # 方法3: 从 self.extras 获取（如果通过 --extras 传递）
        if self.extras:
            extras_to_install.update(e.strip() for e in self.extras.split(","))

        # 执行安装
        valid_extras = {"amazonq", "kiro", "claude", "cursor"}
        for extra in extras_to_install & valid_extras:
            try:
                self._install_rules(extra)
            except Exception as e:
                print(f"Warning: Failed to install rules for {extra}: {e}", file=sys.stderr)

    def _install_rules(self, target_name: str) -> None:
        """复制 rules 到 AI 助手配置目录"""
        # 获取 rules 目录
        package_dir = Path(__file__).parent
        rules_dir = package_dir / "docs" / "rules"

        # 目标目录映射
        target_dirs = {
            "amazonq": Path.home() / ".amazonq" / "rules" / "sqlobjects",
            "kiro": Path.home() / ".kiro" / "rules" / "sqlobjects",
            "claude": Path.home() / ".claude" / "rules" / "sqlobjects",
            "cursor": Path.home() / ".cursor" / "rules" / "sqlobjects",
        }

        target_dir = target_dirs.get(target_name)
        if not target_dir or not rules_dir.exists():
            return

        # 创建目标目录并复制文件
        target_dir.mkdir(parents=True, exist_ok=True)
        copied_count = 0
        for file in rules_dir.glob("*.md"):
            try:
                shutil.copy2(file, target_dir / file.name)
                copied_count += 1
            except Exception:
                pass

        if copied_count > 0:
            print(f"✓ Installed {copied_count} rule files to {target_dir}")


class PostDevelopCommand(develop):
    """Post-installation for development mode."""

    def run(self):
        develop.run(self)
        # 开发模式不自动安装 rules（避免污染开发环境）


setup(
    cmdclass={
        "install": PostInstallCommand,
        "develop": PostDevelopCommand,
    },
)
