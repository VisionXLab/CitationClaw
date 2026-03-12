"""
CitationClaw Agent - 智能体核心逻辑

包含：
- SkillsLoader: 技能加载器
- TaskCoordinator: 任务协调器
"""

from .skills_loader import SkillsLoader
from .task_coordinator import TaskCoordinator

__all__ = ["SkillsLoader", "TaskCoordinator"]
