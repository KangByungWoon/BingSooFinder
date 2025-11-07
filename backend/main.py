from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta
from collections import defaultdict  # ✅ 추가

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
            members = res.json().get("guild_member", [])
            return members
        except Exception as e:
            print(f"[ERROR] JSON 파싱 실패: {e}")
    return []


def get_character_ocid(character_name: str) -> str | None:
    url = f"{BASE_URL}/maplestory/v1/id"
    params = {"character_name": character_name}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        return res.json().get("ocid")
    return None


def get_union_main_character_name(ocid: str) -> str | None:
    url = f"{BASE_URL}/maplestory/v1/ranking/union"
    params = {"date": today, "world_name": "베라", "ocid": ocid}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        data = res.json().get("ranking", [])
        if data:
            return data[0].get("character_name")
    return None


def get_character_guild_name(ocid: str) -> str:
    url = f"{BASE_URL}/maplestory/v1/character/basic"
    params = {"ocid": ocid, "date": today}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        return res.json().get("character_guild_name") or ""
    return ""


@app.get("/kancho-to-bingsoo")
def check_kancho_characters_main_in_bingsoo():
    kancho_members = get_guild_members("칸초")
    if not kancho_members:
        return {"error": "칸초 길드원 조회 실패"}

    matched = []
    c = 0

    for alt in kancho_members:
        if c >= 5:  # ✅ 테스트 제한 유지
            break

        ocid = get_character_ocid(alt)
        if not ocid:
            continue

        main_name = get_union_main_character_name(ocid)
        if not main_name or main_name == alt:
            continue

        main_ocid = get_character_ocid(main_name)
        main_guild_name = get_character_guild_name(main_ocid)

        if main_guild_name == "빙수":
            matched.append({"alt": alt, "main": main_name})

        c += 1

    # ✅ main 기준 그룹화
    grouped = defaultdict(list)
    for entry in matched:
        grouped[entry["main"]].append(entry["alt"])

    result = [{"main": main, "alts": alts} for main, alts in grouped.items()]

    return {"linked_characters": result}