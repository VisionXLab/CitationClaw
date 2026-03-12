"""
Task Coordinator - 任务协调器

协调各个 skill 模块执行完整的论文被引分析工作流。
作为 TaskExecutor 的替代/包装，使用 skills 架构。
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from citationclaw.agent.skills_loader import SkillsLoader
from citationclaw.app.log_manager import LogManager
from citationclaw.app.config_manager import AppConfig


class TaskCoordinator:
    """
    任务协调器 - 使用 Skills 架构协调分析流程

    主要职责：
    1. 通过 SkillsLoader 加载和管理技能
    2. 协调 Phase 1-5 的执行
    3. 保持与 TaskExecutor 相同的接口（向后兼容）
    """

    def __init__(self, log_manager: LogManager, skills_loader: Optional[SkillsLoader] = None):
        """
        初始化任务协调器

        Args:
            log_manager: 日志管理器
            skills_loader: 技能加载器（可选，默认创建）
        """
        self.log_manager = log_manager
        self.skills = skills_loader or SkillsLoader()
        self.current_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.should_cancel = False

        # 保存阶段1的结果
        self.stage1_result: Optional[dict] = None

    def _get_skill(self, name: str, class_name: str = None):
        """获取 skill 类"""
        return self.skills.get_skill_class(name, class_name)

    async def execute_full_pipeline(
        self,
        url: str,
        config: AppConfig,
        output_prefix: str,
        resume_page: int = 0
    ):
        """
        使用 Skills 架构执行完整流程

        此方法作为 TaskExecutor.execute_full_pipeline 的替代
        实际委托给 TaskExecutor 以保持完全兼容
        """
        # 为了保持完全向后兼容，我们使用现有的 task_executor
        # 但这里展示了如何使用 skills 架构

        self.is_running = True
        self.should_cancel = False

        try:
            self.log_manager.info("🎯 使用 Skills 架构执行任务")
            self.log_manager.info(f"📦 可用 Skills:\n{self.skills.build_skills_summary()}")

            # 这里可以逐步迁移到纯 skills 架构
            # 目前保持与原有 TaskExecutor 相同的逻辑

            raise NotImplementedError(
                "TaskCoordinator 需要与 TaskExecutor 集成。"
                "请继续使用 TaskExecutor 直至完整迁移完成。"
            )

        except Exception as e:
            self.log_manager.error(f"任务执行错误: {str(e)}")
            raise
        finally:
            self.is_running = False

    def cancel(self):
        """取消任务"""
        self.should_cancel = True
        self.log_manager.warning("正在取消任务...")

    def get_status(self) -> dict:
        """获取任务状态"""
        return {
            "is_running": self.is_running,
            "should_cancel": self.should_cancel,
            "has_stage1_result": self.stage1_result is not None,
            "skills_available": len(self.skills.list_skills())
        }

    def list_available_skills(self) -> str:
        """列出所有可用的 skills"""
        return self.skills.build_skills_summary()
