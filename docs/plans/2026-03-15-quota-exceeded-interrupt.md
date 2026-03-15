# Quota Exceeded — Global Interrupt & User Notification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When any LLM API call exhausts quota, stop the entire search task cleanly and show an actionable modal to the user instead of hanging indefinitely.

**Architecture:** A shared `asyncio.Event` (`quota_exceeded_event`) is created by `TaskExecutor` at the start of each run and threaded through the skill pipeline. When any searcher hits quota after 3 retries, it sets the event. The executor detects this after each phase and broadcasts a `quota_exceeded` WebSocket event. The frontend renders a dismissible modal explaining what happened and that cached data is safe.

**Tech Stack:** Python asyncio, FastAPI WebSocket, Bootstrap 5 modal (already used for `yearTraverseModal`)

---

### Task 1: Fix infinite quota retry in `author_searcher.py` — add `cancel_event` + bounded retries

**Files:**
- Modify: `citationclaw/core/author_searcher.py`

**Step 1: Add `cancel_event` parameter to `__init__`**

In `__init__` (line 11), add `cancel_event: Optional[asyncio.Event] = None` to the parameter list and store it:

```python
# After line 28 (author_cache: Optional[AuthorInfoCache] = None,)
cancel_event: Optional[asyncio.Event] = None,
```

After line 87 (`self.author_cache: Optional[AuthorInfoCache] = author_cache`), add:

```python
self.cancel_event: Optional[asyncio.Event] = cancel_event
```

**Step 2: Fix `search_fn` quota infinite loop (line 203–206)**

Add `quota_retry_count: int = 0` to `search_fn`'s signature (line 113):
```python
async def search_fn(self, query: str, retry_count: int = 0, max_retries: int = 5, log_prefix: str = "", quota_retry_count: int = 0) -> str:
```

Replace lines 202–206:
```python
# OLD (infinite loop — retry_count never incremented):
if 'rate' in error_msg or 'quota' in error_msg or 'limit' in error_msg:
    self.log_callback("⚠️ API配额超限,等待60秒后重试...")
    await asyncio.sleep(60)
    return await self.search_fn(query, retry_count, max_retries)
```

With:
```python
if 'rate' in error_msg or 'quota' in error_msg or 'limit' in error_msg:
    if quota_retry_count >= 3:
        self.log_callback("❌ API配额持续不足，已停止重试。")
        if self.cancel_event:
            self.cancel_event.set()
        return 'ERROR'
    self.log_callback(f"⚠️ API配额超限，60秒后重试（第{quota_retry_count + 1}/3次）...")
    await asyncio.sleep(60)
    return await self.search_fn(query, retry_count, max_retries, log_prefix, quota_retry_count + 1)
```

**Step 3: Fix `chat_fn` quota infinite loop (line 255–258)**

Add `quota_retry_count: int = 0` to `chat_fn`'s signature (line 221).

Replace lines 254–258 with same pattern as Step 2, calling `self.chat_fn(..., quota_retry_count + 1)`.

**Step 4: Fix `format_fn` quota infinite loop (line 309–312)**

Add `quota_retry_count: int = 0` to `format_fn`'s signature. Replace lines 308–312 with same pattern, calling `self.format_fn(..., quota_retry_count + 1)`.

**Step 5: Fix `verify_fn` quota infinite loop (line 362–365)**

Add `quota_retry_count: int = 0` to `verify_fn`'s signature. Replace lines 361–365 with same pattern, calling `self.verify_fn(..., quota_retry_count + 1)`.

**Step 6: Fix `_check_self_citation_llm` quota infinite loop (line 411–415)**

Add `quota_retry_count: int = 0` to `_check_self_citation_llm`'s signature. Replace lines 410–415:

```python
# OLD:
if 'rate' in error_msg or 'quota' in error_msg or 'limit' in error_msg:
    await asyncio.sleep(60)
    return await self._check_self_citation_llm(
        authors_with_profile, searched_affiliation, retry_count, max_retries
    )
```

With:
```python
if 'rate' in error_msg or 'quota' in error_msg or 'limit' in error_msg:
    if quota_retry_count >= 3:
        self.log_callback("❌ API配额持续不足，已停止重试。")
        if self.cancel_event:
            self.cancel_event.set()
        return False
    self.log_callback(f"⚠️ API配额超限，60秒后重试（第{quota_retry_count + 1}/3次）...")
    await asyncio.sleep(60)
    return await self._check_self_citation_llm(
        authors_with_profile, searched_affiliation, retry_count, max_retries, quota_retry_count + 1
    )
```

**Step 7: Add early-exit check in `_search_single_paper` (line 443)**

At the start of `async with semaphore:` block (after line 443), add:

```python
async with semaphore:
    # Exit immediately if quota has been exceeded by any worker
    if self.cancel_event and self.cancel_event.is_set():
        return (count, {})
    # ... rest of existing code
```

**Step 8: Commit**

```bash
git add citationclaw/core/author_searcher.py
git commit -m "fix: replace infinite quota retry loops with bounded retries + cancel_event in AuthorSearcher"
```

---

### Task 2: Add quota detection + cancel signal to `citing_description_searcher.py`

**Files:**
- Modify: `citationclaw/core/citing_description_searcher.py`

**Step 1: Add `cancel_event` parameter to `__init__`**

Add `cancel_event: Optional[asyncio.Event] = None` to `__init__` (line 14) after `cache: Optional[CitingDescriptionCache] = None`:

```python
cancel_event: Optional[asyncio.Event] = None,
```

After line 36 (`self.cache = cache`), add:
```python
self.cancel_event = cancel_event
```

**Step 2: Add quota detection to `_search_fn` (line 40)**

The current `_search_fn` uses a `for i in range(retries)` loop. Add quota detection in the `except` block (after line 51 where `is_timeout` is set):

```python
except Exception as e:
    error_msg = str(e).lower()
    is_timeout = 'timed out' in error_msg or 'timeout' in error_msg
    is_quota = 'rate' in error_msg or 'quota' in error_msg or 'limit' in error_msg

    if is_quota:
        # Quota errors: signal cancellation immediately (no point retrying rapidly)
        if self.cancel_event and not self.cancel_event.is_set():
            self.log(f"{log_prefix}❌ API配额持续不足，已停止重试。")
            self.cancel_event.set()
        return "NONE"
    if i < retries - 1:
        if i == 0 and not is_timeout:
            self.log(f"{log_prefix}⚠️ 搜索API错误: {e}，正在启用重试机制，请耐心等待！")
        await asyncio.sleep(2 ** i)
    else:
        if not is_timeout:
            self.log(f"{log_prefix}⚠️ 搜索API错误: {e}")
        return "NONE"
```

**Step 3: Add early-exit check in `process_row` (line 117)**

In `process_row`, after the existing `if cancel_check and cancel_check(): return idx, ""` check (line 120), add:

```python
if self.cancel_event and self.cancel_event.is_set():
    return idx, ""
```

**Step 4: Commit**

```bash
git add citationclaw/core/citing_description_searcher.py
git commit -m "fix: add quota detection and cancel_event support to CitingDescriptionSearcher"
```

---

### Task 3: Thread `quota_event` through the skill layer

**Files:**
- Modify: `citationclaw/skills/phase2_author_intel.py`
- Modify: `citationclaw/skills/phase4_citation_desc.py`

**Step 1: Update `phase2_author_intel.py`**

In the `run` method (line 12), add reading the quota event from kwargs and passing it to `AuthorSearcher`:

After line 20 (`author_cache = kwargs.get("author_cache")`), add:
```python
quota_event = kwargs.get("quota_event")
```

In the `AuthorSearcher(...)` constructor call (line 22), add after `author_cache=author_cache,`:
```python
cancel_event=quota_event,
```

**Step 2: Update `phase4_citation_desc.py`**

In the `run` method (line 13), add:

After line 17 (`parallel_workers = kwargs.get(...)`):
```python
quota_event = kwargs.get("quota_event")
```

Update the `cancel_check` passed to `desc_searcher.search()` (line 32) to also check the quota event:
```python
cancel_check=lambda: (ctx.cancel_check() if ctx.cancel_check else False) or (quota_event is not None and quota_event.is_set()),
```

Also pass `cancel_event=quota_event` to `CitingDescriptionSearcher(...)`:
```python
desc_searcher = CitingDescriptionSearcher(
    ...
    cache=desc_cache,
    cancel_event=quota_event,
)
```

**Step 3: Commit**

```bash
git add citationclaw/skills/phase2_author_intel.py citationclaw/skills/phase4_citation_desc.py
git commit -m "feat: pass quota_event through phase2 and phase4 skill layer"
```

---

### Task 4: Create and handle `quota_exceeded_event` in `task_executor.py`

**Files:**
- Modify: `citationclaw/app/task_executor.py`

**Step 1: Initialize `quota_exceeded_event` at run start**

In `execute_full_pipeline` (around line 364–368 where other state is reset), add:

```python
self.quota_exceeded_event = asyncio.Event()
```

**Step 2: Pass `quota_event` kwarg to Phase 2 `_run_skill` call**

Find the `_run_skill("phase2_author_intel", ...)` call (line 536). Add `quota_event=self.quota_exceeded_event` to its kwargs:

```python
await self._run_skill(
    "phase2_author_intel",
    config,
    input_file=citing_file,
    output_file=author_file,
    sleep_seconds=config.sleep_between_authors,
    parallel_workers=config.parallel_author_search,
    citing_paper=canonical,
    target_paper_authors=target_authors,
    author_cache=author_cache,
    quota_event=self.quota_exceeded_event,   # ADD THIS
)
```

**Step 3: Check quota event after Phase 2 completes**

After the existing `if self.should_cancel: break` check following `_run_skill("phase2_author_intel")` (line 547), add:

```python
if self.quota_exceeded_event.is_set():
    self._handle_quota_exceeded()
    return
```

**Step 4: Pass `quota_event` kwarg to Phase 4 `_run_skill` call**

Find the `_run_skill("phase4_citation_desc", ...)` call (line 732). Add `quota_event=self.quota_exceeded_event`:

```python
phase4_result = await self._run_skill(
    "phase4_citation_desc",
    config,
    input_excel=phase4_input,
    output_excel=_phase4_output,
    parallel_workers=config.parallel_author_search,
    quota_event=self.quota_exceeded_event,   # ADD THIS
)
```

**Step 5: Check quota event after Phase 4**

After the `_run_skill("phase4_citation_desc")` call (after line 738), add:

```python
if self.quota_exceeded_event.is_set():
    self._handle_quota_exceeded()
    return
```

**Step 6: Add `_handle_quota_exceeded` helper method**

Add a new method to `TaskExecutor` (near the other helper methods):

```python
def _handle_quota_exceeded(self):
    """Called when any phase signals that API quota is exhausted."""
    self.should_cancel = True
    self.log_manager.error("❌ API 配额不足，搜索已自动停止。已处理的数据已保存至本地缓存。")
    self.log_manager.broadcast_event("quota_exceeded", {
        "message": "API 配额不足，搜索已自动停止。已处理的数据已保存至本地缓存，充值后重新运行将自动续跑，无需重复花费 Token。"
    })
```

**Step 7: Commit**

```bash
git add citationclaw/app/task_executor.py
git commit -m "feat: create quota_exceeded_event in TaskExecutor, broadcast quota_exceeded on exhaustion"
```

---

### Task 5: Add `quotaExceededModal` to `index.html` and handler to `main.js`

**Files:**
- Modify: `citationclaw/templates/index.html`
- Modify: `citationclaw/static/js/main.js`

**Step 1: Add modal HTML to `index.html`**

Find the `<!-- ═══ Year-Traverse Prompt Modal ═══ -->` comment (around line 840). Add the new modal immediately after the closing `</div>` of `yearTraverseModal`:

```html
<!-- ═══ Quota Exceeded Modal ═══ -->
<div class="modal fade" id="quotaExceededModal" tabindex="-1" aria-labelledby="quotaExceededModalLabel" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header border-0 pb-0">
        <h5 class="modal-title" id="quotaExceededModalLabel">
          <i class="bi bi-exclamation-triangle-fill text-danger"></i> API 配额不足，搜索已停止
        </h5>
      </div>
      <div class="modal-body">
        <p id="quota-exceeded-message">
          API 配额不足，搜索已自动停止。
        </p>
        <div class="alert alert-info py-2 mb-0" role="alert" style="font-size:0.88rem">
          <i class="bi bi-info-circle-fill"></i>
          已处理的数据已保存至本地缓存，<strong>充值后重新运行将自动续跑</strong>，无需重复花费 Token。
        </div>
      </div>
      <div class="modal-footer border-0 pt-0">
        <button type="button" class="btn btn-primary" data-bs-dismiss="modal">我知道了</button>
      </div>
    </div>
  </div>
</div>
```

**Step 2: Add WebSocket handler in `main.js`**

Find the `ws.on('year_traverse_prompt', ...)` block (around line 667). Add the new handler immediately after it closes:

```javascript
ws.on('quota_exceeded', data => {
    // Update message if provided
    const msgEl = document.getElementById('quota-exceeded-message');
    if (msgEl && data.message) {
        msgEl.textContent = data.message;
    }
    // Hide progress bar
    GlobalProgress.hide();
    stopRunTimer();
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('quotaExceededModal'));
    modal.show();
});
```

**Step 3: Verify end-to-end manually**

Run the app locally, configure an API key with very low/zero balance, start a search, and confirm:
1. After 3 quota retries the search stops (does not hang)
2. The modal appears with the correct message
3. The progress bar hides
4. On restart, the log shows cache hits for already-processed papers

**Step 4: Commit**

```bash
git add citationclaw/templates/index.html citationclaw/static/js/main.js
git commit -m "feat: add quota_exceeded modal UI and WebSocket handler"
```

---

## Summary of Changes

| File | What Changes |
|------|-------------|
| `citationclaw/core/author_searcher.py` | Add `cancel_event`; fix 5 infinite quota retry loops; early-exit in `_search_single_paper` |
| `citationclaw/core/citing_description_searcher.py` | Add `cancel_event`; quota detection in `_search_fn`; early-exit in `process_row` |
| `citationclaw/skills/phase2_author_intel.py` | Pass `quota_event` kwarg to `AuthorSearcher` |
| `citationclaw/skills/phase4_citation_desc.py` | Pass `quota_event` to `CitingDescriptionSearcher` and `cancel_check` |
| `citationclaw/app/task_executor.py` | Create `quota_exceeded_event`; pass to phases; add `_handle_quota_exceeded` |
| `citationclaw/templates/index.html` | Add `quotaExceededModal` HTML |
| `citationclaw/static/js/main.js` | Add `quota_exceeded` WebSocket event handler |
