"""
Skills Loader - 技能加载器

负责：
1. 加载所有内置 skills
2. 管理工作空间 skills
3. 提供 skills 发现和调用接口
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import shutil

# 默认内置 skills 目录
DEFAULT_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    技能加载器 - 管理 CitationClaw 的所有技能模块

    Skills 是包含 SKILL.md 文件的目录，定义了可复用的功能模块。
    """

    def __init__(
        self,
        workspace: Optional[Path] = None,
        builtin_skills_dir: Optional[Path] = None
    ):
        """
        初始化技能加载器

        Args:
            workspace: 工作空间目录（用于用户自定义 skills）
            builtin_skills_dir: 内置 skills 目录
        """
        self.workspace = workspace or Path("~/.citationclaw").expanduser()
        self.workspace_skills = self.workspace / "skills"
        self.builtin_skills = builtin_skills_dir or DEFAULT_BUILTIN_SKILLS_DIR

    def list_skills(self, filter_unavailable: bool = True) -> List[Dict[str, str]]:
        """
        列出所有可用技能

        Args:
            filter_unavailable: 是否过滤掉依赖未满足的技能

        Returns:
            技能信息列表，每个元素包含 name, path, source, description
        """
        skills = []

        # 1. 工作空间 skills（最高优先级）
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "workspace",
                            "description": self._get_skill_description(skill_dir.name)
                        })

        # 2. 内置 skills
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir() and not skill_dir.name.startswith("__"):
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        # 跳过已存在的工作空间 skill
                        if not any(s["name"] == skill_dir.name for s in skills):
                            skills.append({
                                "name": skill_dir.name,
                                "path": str(skill_file),
                                "source": "builtin",
                                "description": self._get_skill_description(skill_dir.name)
                            })

        # 3. 过滤依赖未满足的技能
        if filter_unavailable:
            skills = [s for s in skills if self._check_requirements(s["name"])]

        return skills

    def load_skill(self, name: str) -> Optional[str]:
        """
        加载指定 skill 的 SKILL.md 内容

        Args:
            name: 技能名称（目录名）

        Returns:
            SKILL.md 内容，未找到返回 None
        """
        # 优先检查工作空间
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # 检查内置
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        return None

    def load_skill_module(self, name: str):
        """
        动态导入 skill 的 Python 模块

        Args:
            name: 技能名称

        Returns:
            技能模块，未找到返回 None
        """
        try:
            # 尝试从内置 skills 导入
            module_name = f"citationclaw.skills.{name}"
            import importlib
            return importlib.import_module(module_name)
        except ImportError:
            return None

    def get_skill_class(self, name: str, class_name: str = None):
        """
        获取 skill 的主类

        Args:
            name: 技能名称
            class_name: 指定类名（可选，默认查找常见名称）

        Returns:
            类对象，未找到返回 None
        """
        module = self.load_skill_module(name)
        if not module:
            return None

        # 如果指定了类名
        if class_name:
            return getattr(module, class_name, None)

        # 常见类名映射
        class_name_map = {
            "google_scholar_scraper": "GoogleScholarScraper",
            "author_searcher": "AuthorSearcher",
            "dashboard_generator": "DashboardGenerator",
            "cache_manager": "AuthorInfoCache",
            "result_exporter": "ResultExporter",
        }

        expected_name = class_name_map.get(name)
        if expected_name:
            return getattr(module, expected_name, None)

        return None

    def build_skills_summary(self) -> str:
        """
        构建所有技能的摘要信息（用于显示）

        Returns:
            格式化的 skills 列表字符串
        """
        skills = self.list_skills(filter_unavailable=False)
        if not skills:
            return "暂无可用技能"

        lines = ["📦 可用 Skills:"]
        for s in skills:
            available = "✅" if self._check_requirements(s["name"]) else "❌"
            emoji = self._get_skill_emoji(s["name"])
            lines.append(f"  {available} {emoji} {s['name']}: {s['description']}")

        return "\n".join(lines)

    def get_always_skills(self) -> List[str]:
        """
        获取标记为 always=true 的技能列表

        Returns:
            always 技能名称列表
        """
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self._get_skill_meta(s["name"])
            if meta.get("always"):
                result.append(s["name"])
        return result

    def _get_skill_description(self, name: str) -> str:
        """从 SKILL.md frontmatter 获取描述"""
        meta = self._parse_skill_frontmatter(name)
        if meta:
            return meta.get("description", name)
        return name

    def _get_skill_emoji(self, name: str) -> str:
        """从 metadata 获取 emoji"""
        meta = self._get_skill_meta(name)
        return meta.get("emoji", "📦")

    def _get_skill_meta(self, name: str) -> Dict[str, Any]:
        """获取 citationclaw 特定的 metadata"""
        meta = self._parse_skill_frontmatter(name)
        if not meta or "metadata" not in meta:
            return {}

        try:
            data = json.loads(meta["metadata"])
            return data.get("citationclaw", {})
        except json.JSONDecodeError:
            return {}

    def _parse_skill_frontmatter(self, name: str) -> Optional[Dict[str, str]]:
        """解析 SKILL.md 的 YAML frontmatter"""
        content = self.load_skill(name)
        if not content:
            return None

        if not content.startswith("---"):
            return None

        # 找到第二个 ---
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        frontmatter = content[3:end_idx].strip()
        metadata = {}

        for line in frontmatter.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip().strip('"\'')

        return metadata

    def _check_requirements(self, name: str) -> bool:
        """检查技能依赖是否满足"""
        meta = self._get_skill_meta(name)
        requires = meta.get("requires", {})

        # 检查必需的命令
        for binary in requires.get("bins", []):
            if not shutil.which(binary):
                return False

        # 检查必需的环境变量
        for env_var in requires.get("env", []):
            if not os.environ.get(env_var):
                # 对于 citationclaw，config.json 中的配置也算满足
                return True  # 暂时返回 True，因为配置可以从文件读取

        return True

    def install_skill(self, name: str, source_path: Path) -> bool:
        """
        安装自定义 skill 到工作空间

        Args:
            name: 技能名称
            source_path: skill 目录路径

        Returns:
            是否安装成功
        """
        if not source_path.exists():
            return False

        target = self.workspace_skills / name
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            import shutil
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source_path, target)
            return True
        except Exception:
            return False

    def uninstall_skill(self, name: str) -> bool:
        """
        从工作空间卸载 skill（只能卸载自定义 skills）

        Args:
            name: 技能名称

        Returns:
            是否卸载成功
        """
        target = self.workspace_skills / name
        if not target.exists():
            return False

        try:
            import shutil
            shutil.rmtree(target)
            return True
        except Exception:
            return False
