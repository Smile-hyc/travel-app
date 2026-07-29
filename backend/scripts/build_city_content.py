"""Build the local Xiaohongshu evidence database one city at a time.

The command deliberately uses one browser process and one city batch at a
time.  Run it without ``--headless`` for the first login, then reuse the saved
browser session for later headless runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main_state import (
    amap_client,
    city_content_pipeline_service,
    review_store,
    tikhub_review_client,
)


async def _run(args: argparse.Namespace) -> None:
    await amap_client.startup()
    try:
        if args.recover_run:
            recovered = city_content_pipeline_service.recover_partial_run(args.recover_run)
            print(json.dumps(recovered, ensure_ascii=False, indent=2))
            return
        city_names = list(dict.fromkeys(args.city or []))
        if args.cities_file:
            city_names.extend(
                line.strip()
                for line in Path(args.cities_file).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        if args.all_cities:
            cities = await city_content_pipeline_service.list_cities()
            if args.province:
                cities = [city for city in cities if city.provinceName == args.province]
            if not args.confirm_all and not args.max_cities:
                raise SystemExit("--all-cities 必须同时提供 --confirm-all 或 --max-cities")
            city_names.extend(city.name for city in cities)
        city_names = list(dict.fromkeys(city_names))
        if args.max_cities:
            city_names = city_names[: args.max_cities]
        if not city_names:
            raise SystemExit("请提供 --city、--cities-file 或 --all-cities")

        results = []
        active_runs = 0
        for index, city_name in enumerate(city_names, 1):
            print(f"[{index}/{len(city_names)}] {city_name}", flush=True)
            stop_after_batch = False
            while True:
                try:
                    if args.plan_only:
                        result = await city_content_pipeline_service.plan_city(
                            city_name,
                            top=args.top,
                        )
                    else:
                        result = await city_content_pipeline_service.run_city_and_wait(
                            city_name,
                            top=args.top,
                            candidate_limit=args.candidate_limit,
                            max_targets=args.max_targets_per_city,
                            headless=args.headless,
                            force_refresh=args.force,
                        )
                    results.append({"cityName": city_name, "result": result})
                    if not args.plan_only and int(result.get("target_count") or 0) > 0:
                        active_runs += 1
                    if not args.plan_only and result.get("status") == "login_required":
                        print(
                            "小红书登录态已失效，已暂停后续城市。请去掉 --headless 扫码后重试。",
                            flush=True,
                        )
                        return
                    if not args.plan_only and result.get("status") == "captcha_required":
                        print(
                            "小红书触发安全验证，当前城市队列已暂停；请人工完成验证后重新运行。",
                            flush=True,
                        )
                        return
                    if not args.plan_only and result.get("status") == "network_unavailable":
                        print(
                            f"小红书网络暂不可用，5 分钟后重试 {city_name}。",
                            flush=True,
                        )
                        await asyncio.sleep(300)
                        continue
                    if not args.plan_only and result.get("error") == "CAPTCHA_REQUIRED":
                        print(
                            "已导入验证码出现前的数据，当前城市队列暂停等待人工验证。",
                            flush=True,
                        )
                        return
                    if args.max_active_cities and active_runs >= args.max_active_cities:
                        print(
                            f"本轮已完成 {active_runs} 个城市批次，停止并保留剩余任务。",
                            flush=True,
                        )
                        stop_after_batch = True
                        break
                    break
                except Exception as exc:
                    if _is_amap_rate_limit_error(exc):
                        print(
                            f"高德 QPS 限流，15 秒后重试 {city_name}。",
                            flush=True,
                        )
                        await asyncio.sleep(15)
                        continue
                    if _is_amap_daily_quota_error(exc) and args.wait_for_quota_reset:
                        delay, resume_at = _quota_reset_delay()
                        print(
                            f"高德日配额已用完，暂停至 {resume_at:%Y-%m-%d %H:%M:%S} 后重试 {city_name}。",
                            flush=True,
                        )
                        await asyncio.sleep(delay)
                        continue
                    results.append(
                        {
                            "cityName": city_name,
                            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                        },
                    )
                    break
            if stop_after_batch:
                break
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        await tikhub_review_client.aclose()
        await amap_client.shutdown()
        review_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="按城市构建热门景点小红书评价库")
    parser.add_argument("--city", action="append", help="可重复提供，例如 --city 北京市")
    parser.add_argument("--cities-file", help="UTF-8 城市名单，每行一个城市")
    parser.add_argument("--all-cities", action="store_true", help="从高德行政区目录读取全部城市")
    parser.add_argument("--province", help="与 --all-cities 配合，只处理指定省份")
    parser.add_argument("--confirm-all", action="store_true", help="确认执行完整全国队列")
    parser.add_argument("--max-cities", type=int, default=0, help="限制本次处理城市数量")
    parser.add_argument("--top", type=int, default=12, choices=range(1, 26))
    parser.add_argument("--candidate-limit", type=int, default=30, choices=range(1, 61))
    parser.add_argument(
        "--max-targets-per-city",
        type=int,
        default=0,
        help="每个城市本轮最多处理的缺失 POI 数；0 表示不限制",
    )
    parser.add_argument(
        "--max-active-cities",
        type=int,
        default=0,
        help="本轮最多实际启动采集的城市数；0 表示不限制",
    )
    parser.add_argument("--headless", action="store_true", help="复用已有登录态无界面运行")
    parser.add_argument("--force", action="store_true", help="忽略缓存刷新全部榜单 POI")
    parser.add_argument("--plan-only", action="store_true", help="只生成 Top 12 榜单和采集清单")
    parser.add_argument("--recover-run", help="从指定任务已落盘的 JSONL 恢复清洗入库")
    parser.add_argument(
        "--wait-for-quota-reset",
        action="store_true",
        help="高德日配额耗尽时暂停到次日 00:05 后继续",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


def _is_amap_daily_quota_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "10003" in message or "DAILY_QUERY_OVER_LIMIT" in message


def _is_amap_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "10021" in message or "CUQPS_HAS_EXCEEDED_THE_LIMIT" in message


def _quota_reset_delay() -> tuple[float, datetime]:
    timezone = ZoneInfo("Asia/Shanghai")
    now = datetime.now(timezone)
    resume_at = (now + timedelta(days=1)).replace(
        hour=0,
        minute=5,
        second=0,
        microsecond=0,
    )
    return max(1.0, (resume_at - now).total_seconds()), resume_at


if __name__ == "__main__":
    main()
