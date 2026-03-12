"""
持久化引用描述缓存（向后兼容模块）。

所有缓存功能已迁移到 citationclaw.skills.cache_manager.citing_description_cache
此文件保留向后兼容的导入路径。
"""
from citationclaw.skills.cache_manager.citing_description_cache import (
    CitingDescriptionCache,
    DEFAULT_DESC_CACHE_FILE as DEFAULT_CACHE_FILE,
)

__all__ = ["CitingDescriptionCache", "DEFAULT_CACHE_FILE"]
