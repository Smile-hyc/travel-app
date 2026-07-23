from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


class MediaCrawlerRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaCrawlerRunResult:
    export_path: Path
    log_path: Path
    return_code: int


class MediaCrawlerRunner:
    """Run one low-concurrency MediaCrawler process for one city."""

    def __init__(
        self,
        *,
        tool_root: str | Path,
        run_root: str | Path,
        timeout_seconds: int = 10800,
    ) -> None:
        self._tool_root = Path(tool_root).expanduser().resolve()
        self._run_root = Path(run_root).expanduser().resolve()
        self._timeout_seconds = max(300, timeout_seconds)
        self._lock = asyncio.Lock()

    @property
    def run_root(self) -> Path:
        return self._run_root

    async def run(
        self,
        *,
        run_id: str,
        city_name: str,
        items: list[dict[str, Any]],
        candidate_limit: int = 30,
        headless: bool = False,
    ) -> MediaCrawlerRunResult:
        if not items:
            raise MediaCrawlerRunError("city collection run has no POI targets")
        python = self._tool_root / ".venv" / "Scripts" / "python.exe"
        entrypoint = self._tool_root / "main.py"
        if not python.is_file() or not entrypoint.is_file():
            raise MediaCrawlerRunError("MediaCrawler runtime is not installed")

        self.cleanup_expired(retention_days=7)
        run_dir = (self._run_root / run_id).resolve()
        if not run_dir.is_relative_to(self._run_root):
            raise MediaCrawlerRunError("invalid crawler run directory")
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "cityName": city_name,
                    "candidateLimit": candidate_limit,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "items": items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        keywords = ",".join(str(item["query_keyword"]) for item in items)
        requested_limit = max(1, min(candidate_limit, 60))
        # XHS search pages contain 20 items and MediaCrawler only requests
        # complete pages. Round up here; the importer still enforces the exact
        # per-POI candidate limit before cleaning.
        crawler_page_limit = max(20, ((requested_limit + 19) // 20) * 20)
        command = [
            str(python),
            str(entrypoint),
            "--platform", "xhs",
            "--lt", "qrcode",
            "--type", "search",
            "--save_data_option", "jsonl",
            "--save_data_path", str(run_dir),
            "--keywords", keywords,
            "--crawler_max_notes_count", str(crawler_page_limit),
            "--max_concurrency_num", "1",
            "--get_comment", "false",
            "--get_sub_comment", "false",
            "--headless", "true" if headless else "false",
        ]

        async with self._lock:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self._tool_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output_task = asyncio.create_task(_read_capped_output(process.stdout))
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError as exc:
                process.terminate()
                await process.wait()
                await output_task
                raise MediaCrawlerRunError("MediaCrawler city run timed out") from exc
            output = await output_task

        log_path = run_dir / "crawler.log"
        log_path.write_bytes(output or b"")
        exports = sorted(
            (run_dir / "xhs" / "jsonl").glob("search_contents_*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if process.returncode != 0:
            output_text = (output or b"").decode("utf-8", errors="replace")
            if "have not found qrcode" in output_text:
                raise MediaCrawlerRunError(
                    "LOGIN_REQUIRED: 小红书登录态已过期，请去掉 --headless 后扫码登录再重试",
                )
            if exports and exports[0].stat().st_size > 0 and _is_captcha_interruption(output_text):
                return MediaCrawlerRunResult(exports[0], log_path, 461)
            if _is_captcha_interruption(output_text):
                raise MediaCrawlerRunError(
                    "CAPTCHA_REQUIRED: 小红书触发安全验证，请在可见浏览器中人工完成验证",
                )
            if _is_network_interruption(output_text):
                raise MediaCrawlerRunError(
                    "NETWORK_UNAVAILABLE: 小红书数据服务暂时无法连接",
                )
            tail = output_text[-800:]
            raise MediaCrawlerRunError(
                f"MediaCrawler exited with code {process.returncode}: {tail}",
            )

        if not exports:
            raise MediaCrawlerRunError("MediaCrawler completed without a JSONL export")
        return MediaCrawlerRunResult(exports[0], log_path, process.returncode or 0)

    def cleanup_expired(self, *, retention_days: int = 7) -> int:
        """Remove only UUID-named crawler runs older than the staging TTL."""
        if not self._run_root.exists():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
        removed = 0
        for path in self._run_root.iterdir():
            if not path.is_dir():
                continue
            try:
                UUID(path.name)
            except ValueError:
                continue
            resolved = path.resolve()
            if resolved.parent != self._run_root:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified >= cutoff:
                continue
            shutil.rmtree(resolved)
            removed += 1
        return removed


async def _read_capped_output(
    stream: asyncio.StreamReader | None,
    *,
    max_bytes: int = 2_000_000,
) -> bytes:
    if stream is None:
        return b""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await stream.read(64 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        while size > max_bytes and chunks:
            removed = chunks.pop(0)
            size -= len(removed)
    return b"".join(chunks)


def _is_captcha_interruption(output: str) -> bool:
    return (
        "CAPTCHA appeared" in output
        or "Verifytype:" in output
        or "status code 461" in output
        or "status code 471" in output
    )


def _is_network_interruption(output: str) -> bool:
    return (
        "All connection attempts failed" in output
        or "ConnectError" in output
        or "ConnectTimeout" in output
        or "ReadTimeout" in output
    )
