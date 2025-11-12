from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import json
import time
from fastapi import Query

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "live_cbf885fa70a2fc14e9482facf3b4c478fe8a851b278223bff0ec1d6017d963ebefe8d04e6d233bd35cf2fabdeb93fb0d"
BASE_URL = "https://open.api.nexon.com"
headers = {"x-nxopen-api-key": API_KEY}
today = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

CACHE_FILE = "cache.json"
CACHE_TTL = 3600  # 60분 (초)


def get_oguild_id(guild_name: str) -> str | None:
    url = f"{BASE_URL}/maplestory/v1/guild/id"
    params = {"guild_name": guild_name, "world_name": "베라"}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        return res.json().get("oguild_id")
    return None


def get_guild_members(guild_name: str) -> list[str]:
    oguild_id = get_oguild_id(guild_name)
    if not oguild_id:
        return []

    url = f"{BASE_URL}/maplestory/v1/guild/basic"
    params = {"oguild_id": oguild_id, "date": today}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        try:
            return res.json().get("guild_member", [])
        except Exception as e:
            print(f"[ERROR] JSON 파싱 실패: {e}")
    return []


def get_character_ocid(character_name: str) -> str | None:
    url = f"{BASE_URL}/maplestory/v1/id"
    params = {"character_name": character_name}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200:
            return res.json().get("ocid")
    except Exception as e:
        print(f"[ERROR] get_character_ocid({character_name}): {e}")
    return None


def get_union_main_character_name(ocid: str) -> str | None:
    url = f"{BASE_URL}/maplestory/v1/ranking/union"
    params = {"date": today, "world_name": "베라", "ocid": ocid}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200:
            data = res.json().get("ranking", [])
            if data and isinstance(data, list):
                return data[0].get("character_name")
    except Exception as e:
        print(f"[ERROR] get_union_main_character_name: {e}")
    return None


def get_character_guild_name(ocid: str) -> str:
    url = f"{BASE_URL}/maplestory/v1/character/basic"
    params = {"ocid": ocid, "date": today}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200:
            return res.json().get("character_guild_name", "")
    except Exception as e:
        print(f"[ERROR] get_character_guild_name: {e}")
    return ""


def process_character(alt: str) -> dict | None:
    try:
        ocid = get_character_ocid(alt)
        if not ocid:
            return None

        main_name = get_union_main_character_name(ocid)
        if not main_name or main_name == alt:
            return None

        main_ocid = get_character_ocid(main_name)
        if not main_ocid:
            return None

        main_guild = get_character_guild_name(main_ocid)
        if main_guild == "빙수":
            return {"alt": alt, "main": main_name}
    except Exception as e:
        print(f"[ERROR] processing {alt}: {e}")
    return None


@app.get("/kancho-to-bingsoo")
def check_kancho_characters_main_in_bingsoo():
    # 캐시가 최신이면 반환
    if os.path.exists(CACHE_FILE):
        last_modified = os.path.getmtime(CACHE_FILE)
        if time.time() - last_modified < CACHE_TTL:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)

    kancho_members = get_guild_members("칸초")
    if not kancho_members:
        return {"error": "칸초 길드원 조회 실패"}

    matched = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_character, alt): alt for alt in kancho_members}
        for future in as_completed(futures):
            result = future.result()
            if result:
                matched.append(result)

    # main 기준 그룹화
    grouped = defaultdict(list)
    for entry in matched:
        grouped[entry["main"]].append(entry["alt"])

    result = [{"main": main, "alts": alts} for main, alts in grouped.items()]
    data = {"linked_characters": result}

    # 캐시 저장
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


@app.post("/kancho-to-bingsoo/reset-cache")
def reset_cache():
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        return {"status": "ok", "message": "캐시 초기화됨"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
@app.get("/character-search")
def search_character(query: str):
    """입력된 닉네임이 main 또는 alt에 포함된 결과 반환"""
    try:
        # 캐시된 데이터 불러오기
        if not os.path.exists(CACHE_FILE):
            return {"error": "데이터가 아직 생성되지 않았습니다."}

        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_chars = data.get("linked_characters", [])
        query_lower = query.lower()

        for entry in all_chars:
            # ✅ main 또는 alts 중 일부라도 일치
            if query_lower in entry["main"].lower() or any(query_lower in alt.lower() for alt in entry["alts"]):
                return {"result": entry}

        # ✅ 일치하는 항목이 없을 때
        return {"result": None}

    except Exception as e:
        return {"error": str(e)}