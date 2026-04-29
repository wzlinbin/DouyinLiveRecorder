from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from . import utils
from .douyin_config import (
    DOUYIN_DOWNLOAD_ROOT,
    DOUYIN_MAX_BATCH_ITEMS,
    DOUYIN_PAGE_DELAY_MAX,
    DOUYIN_PAGE_DELAY_MIN,
    DOUYIN_REQUEST_TIMEOUT,
    DOUYIN_USER_AGENT,
)
from .room import get_xbogus


class DouyinCollectionError(Exception):
    pass


DOUYIN_ALLOWED_HOST_SUFFIXES = (".douyin.com", ".iesdouyin.com", ".snssdk.com")


def validate_douyin_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DouyinCollectionError("仅允许 HTTP(S) 抖音链接")
    host = parsed.hostname or ""
    if host != "douyin.com" and not any(host.endswith(suffix) for suffix in DOUYIN_ALLOWED_HOST_SUFFIXES):
        raise DouyinCollectionError("仅允许抖音相关链接")


@dataclass
class DouyinWork:
    aweme_id: str
    desc: str
    author_name: str
    create_time: int | None
    video_urls: list[str]
    cover_url: str | None = None


@dataclass
class DownloadedFile:
    aweme_id: str
    path: str


def build_headers(cookies: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": DOUYIN_USER_AGENT,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if cookies:
        headers["Cookie"] = cookies
    return headers


def safe_name(text: str, fallback: str = "douyin") -> str:
    cleaned = utils.remove_emojis(text or "")
    cleaned = re.sub(r"[\\/:*?\"<>|&#.。,，~！·\s]+", "_", cleaned).strip("_")
    return cleaned[:80] or fallback


def resolve_output_dir(output_dir: str | None = None) -> Path:
    if not output_dir:
        return DOUYIN_DOWNLOAD_ROOT
    path = Path(output_dir).expanduser()
    if not path.is_absolute():
        path = DOUYIN_DOWNLOAD_ROOT.parent.parent / path
    return path.resolve()


async def resolve_douyin_url(url: str, cookies: str | None = None, proxy: str | None = None) -> str:
    validate_douyin_url(url)
    proxy = utils.handle_proxy_addr(proxy)
    async with httpx.AsyncClient(proxy=proxy, timeout=DOUYIN_REQUEST_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=build_headers(cookies))
        response.raise_for_status()
        resolved_url = str(response.url)
        validate_douyin_url(resolved_url)
        return resolved_url


def parse_aweme_id(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(?:video|note)/(\d+)", parsed.path)
    if match:
        return match.group(1)
    query = parse_qs(parsed.query)
    for key in ("aweme_id", "modal_id", "item_id"):
        if query.get(key):
            return query[key][0]
    raise DouyinCollectionError(f"无法从链接解析作品ID: {url}")


def parse_sec_user_id(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/user/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    query = parse_qs(parsed.query)
    if query.get("sec_user_id"):
        return query["sec_user_id"][0]
    raise DouyinCollectionError(f"无法从链接解析用户sec_user_id: {url}")


def extract_video_urls(aweme: dict) -> list[str]:
    video = aweme.get("video") or {}
    candidates = []
    for key in ("play_addr", "download_addr", "bit_rate"):
        value = video.get(key)
        if isinstance(value, dict):
            candidates.extend(value.get("url_list") or [])
        elif isinstance(value, list):
            for item in value:
                play_addr = (item or {}).get("play_addr") or {}
                candidates.extend(play_addr.get("url_list") or [])
    result = []
    for url in candidates:
        if isinstance(url, str) and url.startswith("http") and url not in result:
            result.append(url.replace("playwm", "play"))
    return result


def parse_work(aweme: dict) -> DouyinWork:
    aweme_id = str(aweme.get("aweme_id") or aweme.get("id") or "")
    if not aweme_id:
        raise DouyinCollectionError("作品详情缺少 aweme_id")
    author = aweme.get("author") or {}
    video_urls = extract_video_urls(aweme)
    if not video_urls:
        raise DouyinCollectionError(f"作品没有可下载视频地址: {aweme_id}")
    cover = ((aweme.get("video") or {}).get("cover") or {}).get("url_list") or []
    return DouyinWork(
        aweme_id=aweme_id,
        desc=aweme.get("desc") or aweme_id,
        author_name=author.get("nickname") or author.get("unique_id") or "douyin",
        create_time=aweme.get("create_time"),
        video_urls=video_urls,
        cover_url=cover[0] if cover else None,
    )


async def signed_get_json(client: httpx.AsyncClient, api: str, params: dict[str, str | int],
                          headers: dict[str, str]) -> dict:
    url = f"{api}?{urlencode(params)}"
    xbogus = await get_xbogus(url, headers=headers)
    response = await client.get(f"{url}&X-Bogus={xbogus}", headers=headers)
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") not in (None, 0):
        raise DouyinCollectionError(f"抖音接口返回错误: {data.get('status_msg') or data.get('status_code')}")
    return data


async def fetch_aweme_detail(aweme_id: str, cookies: str | None = None,
                             proxy: str | None = None) -> DouyinWork:
    proxy = utils.handle_proxy_addr(proxy)
    headers = build_headers(cookies)
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "aweme_id": aweme_id,
    }
    async with httpx.AsyncClient(proxy=proxy, timeout=DOUYIN_REQUEST_TIMEOUT) as client:
        data = await signed_get_json(
            client,
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            params,
            headers,
        )
    aweme = data.get("aweme_detail")
    if not aweme:
        raise DouyinCollectionError("未获取到作品详情，可能需要有效Cookie或链接不可访问")
    return parse_work(aweme)


async def fetch_user_posts(sec_user_id: str, max_items: int = DOUYIN_MAX_BATCH_ITEMS,
                           cookies: str | None = None, proxy: str | None = None) -> list[DouyinWork]:
    max_items = max(1, min(max_items, DOUYIN_MAX_BATCH_ITEMS))
    proxy = utils.handle_proxy_addr(proxy)
    headers = build_headers(cookies)
    cursor = 0
    works: list[DouyinWork] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(proxy=proxy, timeout=DOUYIN_REQUEST_TIMEOUT) as client:
        while len(works) < max_items:
            params = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "sec_user_id": sec_user_id,
                "max_cursor": cursor,
                "locate_query": "false",
                "show_live_replay_strategy": "1",
                "count": min(18, max_items - len(works)),
                "publish_video_strategy_type": "2",
            }
            data = await signed_get_json(
                client,
                "https://www.douyin.com/aweme/v1/web/aweme/post/",
                params,
                headers,
            )
            aweme_list = data.get("aweme_list") or []
            if not aweme_list:
                if not works:
                    raise DouyinCollectionError("未获取到用户作品，可能需要有效Cookie、主页为空或被风控")
                break
            for aweme in aweme_list:
                try:
                    work = parse_work(aweme)
                except DouyinCollectionError:
                    continue
                if work.aweme_id in seen:
                    continue
                seen.add(work.aweme_id)
                works.append(work)
                if len(works) >= max_items:
                    break
            if not data.get("has_more") or len(works) >= max_items:
                break
            cursor = int(data.get("max_cursor") or 0)
            await asyncio.sleep(random.uniform(DOUYIN_PAGE_DELAY_MIN, DOUYIN_PAGE_DELAY_MAX))
    return works


async def fetch_work_from_url(url: str, cookies: str | None = None, proxy: str | None = None) -> DouyinWork:
    resolved_url = await resolve_douyin_url(url, cookies=cookies, proxy=proxy)
    return await fetch_aweme_detail(parse_aweme_id(resolved_url), cookies=cookies, proxy=proxy)


async def fetch_user_works_from_url(url: str, max_items: int = DOUYIN_MAX_BATCH_ITEMS,
                                    cookies: str | None = None, proxy: str | None = None) -> list[DouyinWork]:
    resolved_url = await resolve_douyin_url(url, cookies=cookies, proxy=proxy)
    return await fetch_user_posts(parse_sec_user_id(resolved_url), max_items=max_items, cookies=cookies, proxy=proxy)


async def download_work(work: DouyinWork, output_dir: str | None = None, cookies: str | None = None,
                        proxy: str | None = None, overwrite: bool = False) -> DownloadedFile:
    root = resolve_output_dir(output_dir)
    author_dir = root / safe_name(work.author_name)
    author_dir.mkdir(parents=True, exist_ok=True)
    file_path = author_dir / f"{work.aweme_id}_{safe_name(work.desc, work.aweme_id)}.mp4"
    if file_path.exists() and file_path.stat().st_size > 0 and not overwrite:
        return DownloadedFile(work.aweme_id, str(file_path))

    proxy = utils.handle_proxy_addr(proxy)
    headers = build_headers(cookies)
    last_error = None
    async with httpx.AsyncClient(proxy=proxy, timeout=DOUYIN_REQUEST_TIMEOUT, follow_redirects=True) as client:
        for url in work.video_urls:
            try:
                async with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
                    with temp_path.open("wb") as file:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            if chunk:
                                file.write(chunk)
                    temp_path.replace(file_path)
                    return DownloadedFile(work.aweme_id, str(file_path))
            except Exception as e:
                last_error = e
    raise DouyinCollectionError(f"下载作品失败 {work.aweme_id}: {last_error}")


def run_single_download(url: str, output_dir: str | None = None, cookies: str | None = None,
                        proxy: str | None = None, overwrite: bool = False) -> DownloadedFile:
    async def runner() -> DownloadedFile:
        work = await fetch_work_from_url(url, cookies=cookies, proxy=proxy)
        return await download_work(work, output_dir=output_dir, cookies=cookies, proxy=proxy, overwrite=overwrite)

    return asyncio.run(runner())


def run_user_batch_download(url: str, output_dir: str | None = None, cookies: str | None = None,
                            proxy: str | None = None, max_items: int = DOUYIN_MAX_BATCH_ITEMS,
                            overwrite: bool = False) -> list[DownloadedFile]:
    async def runner() -> list[DownloadedFile]:
        works = await fetch_user_works_from_url(url, max_items=max_items, cookies=cookies, proxy=proxy)
        files = []
        for work in works:
            files.append(await download_work(work, output_dir=output_dir, cookies=cookies, proxy=proxy,
                                             overwrite=overwrite))
            await asyncio.sleep(0.2)
        return files

    return asyncio.run(runner())
