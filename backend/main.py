import os
import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import aiohttp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "live_cbf885fa70a2fc14e9482facf3b4c478fe8a851b278223bff0ec1d6017d963ebefe8d04e6d233bd35cf2fabdeb93fb0d"
BASE_URL = "https://open.api.nexon.com"
HEADERS = {"x-nxopen-api-key": API_KEY}
today = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
CACHE_FILE = "kancho_bingsoo_cache.json"
CACHE_TTL = 600  # 10분

# --------------------- API CALL ---------------------

async def fetch_json(session, url, params):
    async with session.get(url, params=params, headers=HEADERS) as res:
        return await res.json()

async def get_character_ocid(session, name):
    url = f"{BASE_URL}/maplestory/v1/id"
    return (await fetch_json(session, url, {"character_name": name})).get("ocid")

async def get_union_main_name(session, ocid):
    url = f"{BASE_URL}/maplestory/v1/ranking/union"
    data = await fetch_json(session, url, {"ocid": ocid, "world_name": "베라", "date": today})
    return data.get("ranking", [{}])[0].get("character_name")

async def get_character_guild_name(session, ocid):
    url = f"{BASE_URL}/maplestory/v1/character/basic"
    return (await fetch_json(session, url, {"ocid": ocid, "date": today})).get("character_guild_name", "")

async def process_character(session, alt):
    ocid = await get_character_ocid(session, alt)
    if not ocid:
        return None
    main_name = await get_union_main_name(session, ocid)
    if not main_name or main_name == alt:
        return None
    main_ocid = await get_character_ocid(session, main_name)
    if not main_ocid:
        return None
    guild_name = await get_character_guild_name(session, main_ocid)
    if guild_name == "빙수":
        return {"alt": alt, "main": main_name}
    return None

async def get_guild_members(session, guild_name):
    url = f"{BASE_URL}/maplestory/v1/guild/id"
    res = await fetch_json(session, url, {"guild_name": guild_name, "world_name": "베라"})
    oguild_id = res.get("oguild_id")
    if not oguild_id:
        return []
    url = f"{BASE_URL}/maplestory/v1/guild/basic"
    res = await fetch_json(session, url, {"oguild_id": oguild_id, "date": today})
    return res.get("guild_member", [])

# --------------------- 캐싱 및 병렬 집계 ---------------------

@app.get("/kancho-to-bingsoo")
async def check_kancho_characters_main_in_bingsoo():
    # 캐시가 최신이면 리턴
    if os.path.exists(CACHE_FILE) and (datetime.now().timestamp() - os.path.getmtime(CACHE_FILE)) < CACHE_TTL:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    async with aiohttp.ClientSession() as session:
        kancho_members = await get_guild_members(session, "칸초")
        tasks = [process_character(session, alt) for alt in kancho_members]
        results = await asyncio.gather(*tasks)

    filtered = [r for r in results if r]

    # main 이름 기준으로 alt 병합
    grouped = {}
    for entry in filtered:
        main = entry["main"]
        if main not in grouped:
            grouped[main] = []
        grouped[main].append(entry["alt"])

    linked_characters = [{"main": main, "alt": ", ".join(alts)} for main, alts in grouped.items()]

    # 캐시 저장
    data = {"linked_characters": linked_characters}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data