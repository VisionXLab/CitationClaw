"""
CitationClaw Core - 向后兼容模块

所有核心功能已迁移到 skills 模块。
此模块保留向后兼容的导入路径。
"""

# 从 skills 模块导入以保持向后兼容
from citationclaw.skills.google_scholar_scraper import GoogleScholarScraper
from citationclaw.skills.author_searcher import AuthorSearcher
from citationclaw.skills.dashboard_generator import DashboardGenerator
from citationclaw.skills.cache_manager import AuthorInfoCache
from citationclaw.skills.result_exporter import ResultExporter
from citationclaw.skills.google_scholar_scraper.parser import google_scholar_html_parser

__all__ = [
    "GoogleScholarScraper",
    "AuthorSearcher",
    "DashboardGenerator",
    "AuthorInfoCache",
    "ResultExporter",
    "google_scholar_html_parser",
]
