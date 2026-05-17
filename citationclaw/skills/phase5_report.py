from __future__ import annotations

import asyncio
from pathlib import Path

from citationclaw.skills.base import SkillContext, SkillResult
from citationclaw.core.dashboard_generator import DashboardGenerator


class ReportGenerateSkill:
    name = "phase5_report_generate"

    async def run(self, ctx: SkillContext, **kwargs) -> SkillResult:
        try:
            return await self._run_inner(ctx, **kwargs)
        except Exception as e:
            ctx.log(f"[Phase5] fatal error: {e}")
            raise

    async def _run_inner(self, ctx: SkillContext, **kwargs) -> SkillResult:
        config = ctx.config
        citing_desc_excel = Path(kwargs["citing_desc_excel"])
        renowned_all_xlsx = Path(kwargs["renowned_all_xlsx"])
        renowned_top_xlsx = Path(kwargs["renowned_top_xlsx"])
        output_html = Path(kwargs["output_html"])
        canonical_titles = kwargs.get("canonical_titles")
        download_filenames = kwargs.get("download_filenames")
        skip_citing_analysis = kwargs.get("skip_citing_analysis", False)

        ctx.log("[Phase5] Generating HTML dashboard report...")

        gen = DashboardGenerator(
            api_key=config.effective_light_api_key(),
            base_url=config.effective_light_base_url(),
            model=config.dashboard_model,
            log_callback=ctx.log,
            test_mode=config.test_mode,
        )

        ctx.log("[Phase5] Running dashboard generator...")
        gen.generate(
            citing_desc_excel=citing_desc_excel,
            renowned_all_xlsx=renowned_all_xlsx,
            renowned_top_xlsx=renowned_top_xlsx,
            output_html=output_html,
            canonical_titles=canonical_titles,
            download_filenames=download_filenames,
            skip_citing_analysis=skip_citing_analysis,
        )

        ctx.log(f"[Phase5] Report saved to {output_html}")
        return SkillResult(name=self.name, data={"output_html": str(output_html)})
