import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from core.scraper import GoogleScholarScraper
from core.author_searcher import AuthorSearcher
from core.exporter import ResultExporter
from app.log_manager import LogManager
from app.config_manager import AppConfig


class TaskExecutor:
    def __init__(self, log_manager: LogManager):
        """
        任务执行器,负责协调整个工作流

        Args:
            log_manager: 日志管理器
        """
        self.log_manager = log_manager
        self.current_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.should_cancel = False

        # 保存阶段1的结果，供阶段2使用
        self.stage1_result: Optional[dict] = None

    async def execute_full_pipeline(
        self,
        url: str,
        config: AppConfig,
        output_prefix: str,
        resume_page: int = 0
    ):
        """
        执行完整流程:抓取 -> 搜索作者 -> 导出

        Args:
            url: Google Scholar引用列表URL
            config: 应用配置
            output_prefix: 输出文件前缀
            resume_page: 断点续爬起始页
        """
        self.is_running = True
        self.should_cancel = False

        try:
            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_prefix = f"{output_prefix}-{timestamp}"

            self.log_manager.info(f"📁 文件前缀: {file_prefix}")

            # ==================== 阶段1: 抓取引用列表 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段1: 开始抓取Google Scholar引用列表")
            self.log_manager.info("=" * 50)

            scraper = GoogleScholarScraper(
                api_keys=config.scraper_api_keys,
                log_callback=self.log_manager.info,
                progress_callback=self.log_manager.update_progress,
                debug_mode=config.debug_mode,
                premium=config.scraper_premium,
                ultra_premium=config.scraper_ultra_premium,
                retry_max_attempts=config.retry_max_attempts,
                retry_intervals=config.retry_intervals,
                session=config.scraper_session,
                no_filter=config.scholar_no_filter,
                geo_rotate=config.scraper_geo_rotate,
                dc_retry_max_attempts=config.dc_retry_max_attempts,
            )

            citing_papers_file = Path(f"data/jsonl/{file_prefix}_citing_papers.jsonl")
            await scraper.scrape(
                url=url,
                output_file=citing_papers_file,
                start_page=resume_page,
                sleep_seconds=config.sleep_between_pages,
                cancel_check=lambda: self.should_cancel,
                enable_year_traverse=config.enable_year_traverse
            )

            if self.should_cancel:
                self.log_manager.warning("任务已被用户取消")
                return

            self.log_manager.success("阶段1完成: 引用列表抓取成功")

            # ==================== 阶段2: 搜索作者信息 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段2: 开始搜索作者学术信息")
            self.log_manager.info("=" * 50)

            searcher = AuthorSearcher(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
                model=config.openai_model,
                log_callback=self.log_manager.info,
                progress_callback=self.log_manager.update_progress,
                prompt1=config.author_search_prompt1,
                prompt2=config.author_search_prompt2,
                enable_renowned_scholar=config.enable_renowned_scholar_filter,
                renowned_scholar_model=config.renowned_scholar_model,
                renowned_scholar_prompt=config.renowned_scholar_prompt,
                enable_author_verification=config.enable_author_verification,
                author_verify_model=config.author_verify_model,
                author_verify_prompt=config.author_verify_prompt,
                debug_mode=config.debug_mode
            )

            author_info_file = Path(f"data/jsonl/{file_prefix}_author_information.jsonl")
            await searcher.search(
                input_file=citing_papers_file,
                output_file=author_info_file,
                sleep_seconds=config.sleep_between_authors,
                parallel_workers=config.parallel_author_search,
                cancel_check=lambda: self.should_cancel
            )

            if self.should_cancel:
                self.log_manager.warning("任务已被用户取消")
                return

            self.log_manager.success("阶段2完成: 作者信息搜索成功")

            # ==================== 阶段3: 导出结果 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段3: 开始导出结果")
            self.log_manager.info("=" * 50)

            exporter = ResultExporter(log_callback=self.log_manager.info)

            excel_file = Path(f"data/excel/{file_prefix}_author_information.xlsx")
            json_file = Path(f"data/json/{file_prefix}_author_information.json")

            await exporter.export(
                input_file=author_info_file,
                excel_output=excel_file,
                json_output=json_file
            )

            self.log_manager.success("=" * 50)
            self.log_manager.success("全部任务完成!")
            self.log_manager.success(f"Excel文件: {excel_file}")
            self.log_manager.success(f"JSON文件: {json_file}")
            self.log_manager.success("=" * 50)

        except Exception as e:
            self.log_manager.error(f"任务执行错误: {str(e)}")
            import traceback
            self.log_manager.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False

    async def execute_stage1_scraping(
        self,
        url: str,
        config: AppConfig,
        output_prefix: str,
        resume_page: int = 0
    ):
        """
        执行阶段1: 抓取引用列表

        Args:
            url: Google Scholar引用列表URL
            config: 应用配置
            output_prefix: 输出文件前缀
            resume_page: 断点续爬起始页
        """
        self.is_running = True
        self.should_cancel = False

        try:
            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_prefix = f"{output_prefix}-{timestamp}"

            self.log_manager.info(f"📁 文件前缀: {file_prefix}")

            # ==================== 阶段1: 抓取引用列表 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段1: 开始抓取Google Scholar引用列表")
            self.log_manager.info("=" * 50)

            scraper = GoogleScholarScraper(
                api_keys=config.scraper_api_keys,
                log_callback=self.log_manager.info,
                progress_callback=self.log_manager.update_progress,
                debug_mode=config.debug_mode,
                premium=config.scraper_premium,
                ultra_premium=config.scraper_ultra_premium,
                retry_max_attempts=config.retry_max_attempts,
                retry_intervals=config.retry_intervals,
                session=config.scraper_session,
                no_filter=config.scholar_no_filter,
                geo_rotate=config.scraper_geo_rotate,
                dc_retry_max_attempts=config.dc_retry_max_attempts,
            )

            citing_papers_file = Path(f"data/jsonl/{file_prefix}_citing_papers.jsonl")
            await scraper.scrape(
                url=url,
                output_file=citing_papers_file,
                start_page=resume_page,
                sleep_seconds=config.sleep_between_pages,
                cancel_check=lambda: self.should_cancel,
                enable_year_traverse=config.enable_year_traverse
            )

            if self.should_cancel:
                self.log_manager.warning("任务已被用户取消")
                return

            self.log_manager.success("=" * 50)
            self.log_manager.success("✅ 阶段1完成: 引用列表抓取成功")
            self.log_manager.success(f"📄 输出文件: {citing_papers_file}")
            self.log_manager.success("=" * 50)

            # 保存阶段1结果供阶段2使用
            self.stage1_result = {
                "file_prefix": file_prefix,
                "citing_papers_file": str(citing_papers_file),
                "config": config
            }

            # 发送阶段1完成通知
            await self.log_manager._broadcast({
                "type": "stage1_complete",
                "data": {
                    "file_prefix": file_prefix,
                    "citing_papers_file": str(citing_papers_file)
                }
            })

        except Exception as e:
            self.log_manager.error(f"阶段1执行错误: {str(e)}")
            import traceback
            self.log_manager.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False

    async def import_history(self, file_path: Path, config: AppConfig) -> dict:
        """
        导入历史抓取记录

        Args:
            file_path: 导入的jsonl文件路径
            config: 应用配置

        Returns:
            导入结果信息
        """
        try:
            import json

            if not file_path.exists():
                return {"success": False, "message": "文件不存在"}

            # 读取文件并统计论文数
            paper_count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line)
                    for page_id, page_content in data.items():
                        paper_dict = page_content.get('paper_dict', {})
                        paper_count += len(paper_dict)

            # 复制文件到data/jsonl目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_prefix = f"imported-{timestamp}"
            target_path = Path(f"data/jsonl/{file_prefix}_citing_papers.jsonl")
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            import shutil
            shutil.copy2(file_path, target_path)

            # 保存阶段1结果供阶段2使用
            self.stage1_result = {
                "file_prefix": file_prefix,
                "citing_papers_file": str(target_path),
                "config": config
            }

            self.log_manager.success(f"✅ 成功导入历史记录: {file_path.name}")
            self.log_manager.info(f"📄 论文数量: {paper_count}")
            self.log_manager.info(f"📁 保存位置: {target_path}")

            return {
                "success": True,
                "file_name": file_path.name,
                "paper_count": paper_count,
                "file_prefix": file_prefix
            }

        except Exception as e:
            self.log_manager.error(f"❌ 导入失败: {str(e)}")
            return {"success": False, "message": str(e)}

    async def execute_stage2_and_3(self):
        """
        执行阶段2和3: 搜索作者信息 + 导出结果
        需要先执行阶段1，或者有保存的阶段1结果
        """
        if not self.stage1_result:
            self.log_manager.error("❌ 错误: 未找到阶段1的结果，请先执行阶段1或导入历史记录")
            return

        self.is_running = True
        self.should_cancel = False

        try:
            file_prefix = self.stage1_result["file_prefix"]
            citing_papers_file = Path(self.stage1_result["citing_papers_file"])
            config = self.stage1_result["config"]

            # ==================== 阶段2: 搜索作者信息 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段2: 开始搜索作者学术信息")
            self.log_manager.info("=" * 50)

            searcher = AuthorSearcher(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
                model=config.openai_model,
                log_callback=self.log_manager.info,
                progress_callback=self.log_manager.update_progress,
                prompt1=config.author_search_prompt1,
                prompt2=config.author_search_prompt2,
                enable_renowned_scholar=config.enable_renowned_scholar_filter,
                renowned_scholar_model=config.renowned_scholar_model,
                renowned_scholar_prompt=config.renowned_scholar_prompt,
                enable_author_verification=config.enable_author_verification,
                author_verify_model=config.author_verify_model,
                author_verify_prompt=config.author_verify_prompt,
                debug_mode=config.debug_mode
            )

            author_info_file = Path(f"data/jsonl/{file_prefix}_author_information.jsonl")
            await searcher.search(
                input_file=citing_papers_file,
                output_file=author_info_file,
                sleep_seconds=config.sleep_between_authors,
                parallel_workers=config.parallel_author_search,
                cancel_check=lambda: self.should_cancel
            )

            if self.should_cancel:
                self.log_manager.warning("任务已被用户取消")
                return

            self.log_manager.success("阶段2完成: 作者信息搜索成功")

            # ==================== 阶段3: 导出结果 ====================
            self.log_manager.info("=" * 50)
            self.log_manager.info("阶段3: 开始导出结果")
            self.log_manager.info("=" * 50)

            exporter = ResultExporter(log_callback=self.log_manager.info)

            excel_file = Path(f"data/excel/{file_prefix}_author_information.xlsx")
            json_file = Path(f"data/json/{file_prefix}_author_information.json")

            exporter.export(
                input_file=author_info_file,
                excel_output=excel_file,
                json_output=json_file
            )

            self.log_manager.success("=" * 50)
            self.log_manager.success("全部任务完成!")
            self.log_manager.success(f"Excel文件: {excel_file}")
            self.log_manager.success(f"JSON文件: {json_file}")
            self.log_manager.success("=" * 50)

            # 清空阶段1结果
            self.stage1_result = None

        except Exception as e:
            self.log_manager.error(f"阶段2/3执行错误: {str(e)}")
            import traceback
            self.log_manager.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False

    async def execute_for_titles(
        self,
        paper_titles: List[str],
        config: AppConfig,
        output_prefix: str,
    ):
        """
        全自动多论文流水线：
          对每篇论文：Phase 1（爬取引用）+ Phase 2（搜索作者）
          最终合并所有结果 → Phase 3（导出 Excel/JSON）
        """
        from core.url_finder import PaperURLFinder

        self.is_running = True
        self.should_cancel = False

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # All output files go into a single result folder
            result_dir = Path(f"data/result-{timestamp}")
            result_dir.mkdir(parents=True, exist_ok=True)
            self.log_manager.info(f"📁 结果目录: {result_dir}")

            url_finder = PaperURLFinder(
                api_keys=config.scraper_api_keys,
                log_callback=self.log_manager.info,
                retry_max_attempts=config.retry_max_attempts,
                retry_intervals=config.retry_intervals,
            )

            author_info_files = []   # 收集每篇论文的 Phase 2 输出

            total = len(paper_titles)
            for i, title in enumerate(paper_titles):
                if self.should_cancel:
                    break

                self.log_manager.info("=" * 50)
                self.log_manager.info(f"📄 论文 {i+1}/{total}: {title}")
                self.log_manager.info("=" * 50)

                # —— 查找引用 URL ——
                url = url_finder.find_citation_url(title)
                if not url:
                    self.log_manager.warning(f"⚠️ 跳过（未找到引用链接）: {title}")
                    continue

                paper_slug = f"paper{i+1}"

                # —— Phase 1：爬取引用列表 ——
                self.log_manager.info("▶ Phase 1: 爬取引用列表")
                scraper = GoogleScholarScraper(
                    api_keys=config.scraper_api_keys,
                    log_callback=self.log_manager.info,
                    progress_callback=self.log_manager.update_progress,
                    debug_mode=config.debug_mode,
                    premium=config.scraper_premium,
                    ultra_premium=config.scraper_ultra_premium,
                    retry_max_attempts=config.retry_max_attempts,
                    retry_intervals=config.retry_intervals,
                    session=config.scraper_session,
                    no_filter=config.scholar_no_filter,
                    geo_rotate=config.scraper_geo_rotate,
                )
                citing_file = result_dir / f"{paper_slug}_citing.jsonl"
                await scraper.scrape(
                    url=url,
                    output_file=citing_file,
                    start_page=0,
                    sleep_seconds=config.sleep_between_pages,
                    cancel_check=lambda: self.should_cancel,
                    enable_year_traverse=config.enable_year_traverse,
                )
                if self.should_cancel:
                    break

                # —— Phase 2：搜索作者信息 ——
                self.log_manager.info("▶ Phase 2: 搜索作者信息")
                searcher = AuthorSearcher(
                    api_key=config.openai_api_key,
                    base_url=config.openai_base_url,
                    model=config.openai_model,
                    log_callback=self.log_manager.info,
                    progress_callback=self.log_manager.update_progress,
                    prompt1=config.author_search_prompt1,
                    prompt2=config.author_search_prompt2,
                    enable_renowned_scholar=config.enable_renowned_scholar_filter,
                    renowned_scholar_model=config.renowned_scholar_model,
                    renowned_scholar_prompt=config.renowned_scholar_prompt,
                    enable_author_verification=config.enable_author_verification,
                    author_verify_model=config.author_verify_model,
                    author_verify_prompt=config.author_verify_prompt,
                    debug_mode=config.debug_mode,
                )
                author_file = result_dir / f"{paper_slug}_authors.jsonl"
                await searcher.search(
                    input_file=citing_file,
                    output_file=author_file,
                    sleep_seconds=config.sleep_between_authors,
                    parallel_workers=config.parallel_author_search,
                    cancel_check=lambda: self.should_cancel,
                    citing_paper=title,
                )
                if self.should_cancel:
                    break
                author_info_files.append(author_file)

            if not author_info_files:
                self.log_manager.warning("没有成功处理的论文，任务结束")
                return

            # —— 合并所有 author JSONL ——
            merged_file = result_dir / "merged_authors.jsonl"
            with open(merged_file, "w", encoding="utf-8") as out_f:
                for af in author_info_files:
                    if af.exists():
                        out_f.write(af.read_text(encoding="utf-8"))

            # —— Phase 3：导出 ——
            self.log_manager.info("▶ Phase 3: 导出结果")
            exporter = ResultExporter(log_callback=self.log_manager.info)
            excel_file = result_dir / f"{output_prefix}_results.xlsx"
            json_file = result_dir / f"{output_prefix}_results.json"
            exporter.export(
                input_file=merged_file,
                excel_output=excel_file,
                json_output=json_file,
            )

            # —— Phase 4：搜索引用描述（可选）——
            citing_desc_excel = excel_file
            if config.enable_citing_description:
                self.log_manager.info("▶ Phase 4: 搜索引用描述")
                from core.citing_description_searcher import CitingDescriptionSearcher
                desc_searcher = CitingDescriptionSearcher(
                    api_key=config.openai_api_key,
                    base_url=config.openai_base_url,
                    model=config.openai_model,
                    log_callback=self.log_manager.info,
                    progress_callback=self.log_manager.update_progress,
                )
                citing_desc_excel = result_dir / f"{output_prefix}_results_with_citing_desc.xlsx"
                await desc_searcher.search(
                    input_excel=excel_file,
                    output_excel=citing_desc_excel,
                    parallel_workers=config.parallel_author_search,
                    cancel_check=lambda: self.should_cancel,
                )

            # —— Phase 5：生成 HTML 画像报告（可选）——
            html_file = None
            if config.enable_dashboard:
                self.log_manager.info("▶ Phase 5: 生成 HTML 画像报告")
                from core.dashboard_generator import DashboardGenerator
                html_file = result_dir / f"{output_prefix}_dashboard.html"

                all_renowned = excel_file.with_stem(excel_file.stem + "_all_renowned_scholar")
                top_renowned = excel_file.with_stem(excel_file.stem + "_top-tier_scholar")

                gen = DashboardGenerator(
                    api_key=config.openai_api_key,
                    base_url=config.openai_base_url,
                    model=config.dashboard_model,
                    log_callback=self.log_manager.info,
                )
                gen.generate(
                    citing_desc_excel=citing_desc_excel,
                    renowned_all_xlsx=all_renowned,
                    renowned_top_xlsx=top_renowned,
                    output_html=html_file,
                    download_filenames={
                        "excel": citing_desc_excel.name,   # with_citing_desc if Phase 4 ran, else base
                        "all_renowned": all_renowned.name,
                        "top_renowned": top_renowned.name,
                    },
                )

            self.log_manager.success("=" * 50)
            self.log_manager.success("✅ 全部完成!")
            self.log_manager.success(f"📊 Excel: {excel_file}")
            self.log_manager.success(f"📋 JSON:  {json_file}")
            if html_file:
                self.log_manager.success(f"📊 Dashboard: {html_file}")
            self.log_manager.success("=" * 50)
            await self.log_manager._broadcast({"type": "all_done", "data": {
                "excel": str(excel_file),
                "json": str(json_file),
                "dashboard": str(html_file) if html_file else None,
            }})

        except Exception as e:
            self.log_manager.error(f"任务错误: {e}")
            import traceback; self.log_manager.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False

    def cancel(self):
        """取消任务"""
        if self.is_running:
            self.should_cancel = True
            self.log_manager.warning("正在取消任务...")

    def get_status(self) -> dict:
        """
        获取任务状态

        Returns:
            状态信息
        """
        return {
            "is_running": self.is_running,
            "should_cancel": self.should_cancel,
            "has_stage1_result": self.stage1_result is not None
        }
