"""
CitationClaw Skills - 模块化技能系统

所有功能已拆分为独立的 skill 模块，每个模块包含：
- SKILL.md: 技能说明文档
- 对应 Python 模块: 实现逻辑
"""

from pathlib import Path

# Default skills directory
DEFAULT_SKILLS_DIR = Path(__file__).parent

__all__ = ["DEFAULT_SKILLS_DIR"]
