"""
[JS-K010] 한국 주식 정보 조회 스킬
KOSPI/KOSDAQ 종목명 또는 6자리 티커로 실시간 주식 정보를 조회합니다.

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: httpx>=0.28
"""

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from jedisos.forge.decorator import tool

# Naver 자동완성 API (종목명 → 코드 변환)
_AC_URL = "https://ac.stock.naver.com/ac"
# Naver 실시간 시세 API (코드 → 데이터)
_POLLING_URL = "https://polling.finance.naver.com/api/realtime"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JediSOS/1.0)"}


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _format_price(v: float | None) -> str | None:
    if v is None:
        return None
    return f"{abs(int(v)):,}"


def _format_index(v: float | None) -> str | None:
    """지수 값 포맷 (100으로 나눠서 소수점 표시)."""
    if v is None:
        return None
    return f"{abs(v) / 100:,.2f}"


def _is_ticker(q: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", q.strip()))


def _is_index_query(q: str) -> str | None:
    t = q.strip().upper().replace(" ", "")
    mapping = {
        "KOSPI": "KOSPI",
        "코스피": "KOSPI",
        "KOSPI지수": "KOSPI",
        "코스피지수": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "코스닥": "KOSDAQ",
        "KOSDAQ지수": "KOSDAQ",
        "코스닥지수": "KOSDAQ",
    }
    return mapping.get(t)


def _change_sign(rf: str) -> str:
    """rf 코드 → 부호. 1=상한, 2=상승, 3=보합, 4=하한, 5=하락."""
    return {"1": "+", "2": "+", "3": "", "4": "-", "5": "-"}.get(rf, "")


async def _search_stock(query: str) -> dict[str, Any]:
    """종목명으로 코드를 검색합니다."""
    params = {"q": query, "target": "stock"}
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(_AC_URL, params=params)
        r.raise_for_status()
        data = r.json()

    items = data.get("items") or []
    if not items:
        return {"ok": False, "error": f"'{query}' 종목을 찾지 못했습니다.", "candidates": []}

    candidates = [
        {
            "code": item["code"],
            "name": item["name"],
            "market": item.get("typeName", ""),
        }
        for item in items[:5]
    ]

    return {"ok": True, "best": candidates[0], "candidates": candidates}


async def _fetch_stock_data(code: str) -> dict[str, Any]:
    """종목 코드로 실시간 시세를 조회합니다."""
    url = f"{_POLLING_URL}?query=SERVICE_ITEM:{quote(code)}"
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(url)
        r.raise_for_status()
        text = r.content.decode("euc-kr")
        data = json.loads(text)

    areas = (data.get("result") or {}).get("areas") or []
    if not areas or not areas[0].get("datas"):
        return {"ok": False, "error": "시세 데이터를 받지 못했습니다."}

    d = areas[0]["datas"][0]
    sign = _change_sign(d.get("rf", ""))
    cv = _safe_float(d.get("cv"))
    nv = _safe_float(d.get("nv"))

    # PER 계산 (현재가 / EPS)
    eps = _safe_float(d.get("eps"))
    per = round(nv / eps, 2) if nv and eps and eps > 0 else None

    # PBR 계산 (현재가 / BPS)
    bps = _safe_float(d.get("bps"))
    pbr = round(nv / bps, 2) if nv and bps and bps > 0 else None

    return {
        "ok": True,
        "code": d.get("cd"),
        "name": d.get("nm"),
        "price": nv,
        "change": cv,
        "change_sign": sign,
        "change_rate": _safe_float(d.get("cr")),
        "open": _safe_float(d.get("ov")),
        "high": _safe_float(d.get("hv")),
        "low": _safe_float(d.get("lv")),
        "volume": _safe_float(d.get("aq")),
        "trade_amount": _safe_float(d.get("aa")),
        "prev_close": _safe_float(d.get("pcv") or d.get("sv")),
        "upper_limit": _safe_float(d.get("ul")),
        "lower_limit": _safe_float(d.get("ll")),
        "eps": eps,
        "bps": bps,
        "per": per,
        "pbr": pbr,
        "dividend": _safe_float(d.get("dv")),
        "market_status": d.get("ms"),
    }


async def _fetch_index_data(index: str) -> dict[str, Any]:
    """KOSPI/KOSDAQ 지수를 조회합니다."""
    url = f"{_POLLING_URL}?query=SERVICE_INDEX:{quote(index)}"
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(url)
        r.raise_for_status()
        text = r.content.decode("euc-kr")
        data = json.loads(text)

    areas = (data.get("result") or {}).get("areas") or []
    if not areas or not areas[0].get("datas"):
        return {"ok": False, "error": "지수 데이터를 받지 못했습니다."}

    d = areas[0]["datas"][0]
    sign = _change_sign(d.get("rf", ""))

    return {
        "ok": True,
        "index": d.get("cd"),
        "value": _safe_float(d.get("nv")),
        "change": _safe_float(d.get("cv")),
        "change_sign": sign,
        "change_rate": _safe_float(d.get("cr")),
        "open": _safe_float(d.get("ov")),
        "high": _safe_float(d.get("hv")),
        "low": _safe_float(d.get("lv")),
        "volume": _safe_float(d.get("aq")),
        "market_status": d.get("ms"),
    }


def _stock_summary(data: dict[str, Any], market: str = "") -> str:
    """주식 데이터를 한국어 요약 문자열로 변환합니다."""
    name = data.get("name", "?")
    price = _format_price(data.get("price"))
    sign = data.get("change_sign", "")
    change = _format_price(data.get("change"))
    rate = data.get("change_rate")
    status = "장마감" if data.get("market_status") == "CLOSE" else "거래중"

    parts = [f"{name}({data.get('code', '')})"]
    if market:
        parts[0] += f" [{market}]"
    if price:
        parts.append(f"현재가 {price}원")
    if change and rate is not None:
        parts.append(f"전일대비 {sign}{change}원 ({sign}{abs(rate)}%)")
    parts.append(status)

    sub = []
    if data.get("open"):
        sub.append(f"시가 {_format_price(data['open'])}")
    if data.get("high"):
        sub.append(f"고가 {_format_price(data['high'])}")
    if data.get("low"):
        sub.append(f"저가 {_format_price(data['low'])}")
    if data.get("volume"):
        sub.append(f"거래량 {int(data['volume']):,}")
    if sub:
        parts.append(" / ".join(sub))

    indicators = []
    if data.get("per"):
        indicators.append(f"PER {data['per']}")
    if data.get("pbr"):
        indicators.append(f"PBR {data['pbr']}")
    if data.get("dividend"):
        indicators.append(f"배당금 {_format_price(data['dividend'])}원")
    if indicators:
        parts.append(" / ".join(indicators))

    return " | ".join(parts)


def _index_summary(data: dict[str, Any]) -> str:
    """지수 데이터를 한국어 요약 문자열로 변환합니다."""
    index = data.get("index", "?")
    value = _format_index(data.get("value"))
    sign = data.get("change_sign", "")
    change = _format_index(data.get("change"))
    rate = data.get("change_rate")
    status = "장마감" if data.get("market_status") == "CLOSE" else "거래중"

    parts = [f"{index} {value}"]
    if change and rate is not None:
        parts.append(f"전일대비 {sign}{change}p ({sign}{abs(rate)}%)")
    parts.append(status)

    sub = []
    if data.get("open"):
        sub.append(f"시가 {_format_index(data['open'])}")
    if data.get("high"):
        sub.append(f"고가 {_format_index(data['high'])}")
    if data.get("low"):
        sub.append(f"저가 {_format_index(data['low'])}")
    if sub:
        parts.append(" / ".join(sub))

    return " | ".join(parts)


@tool(
    name="kr_stock_info",
    description="한국 주식(KOSPI/KOSDAQ) 종목명(삼성전자) 또는 6자리 티커(005930)로 실시간 현재가, 등락률, 거래량, PER, PBR 등을 조회합니다. 'KOSPI 지수', 'KOSDAQ 지수'도 조회 가능합니다.",
)
async def kr_stock_info(query: str) -> dict:
    """한국 주식/지수 실시간 정보를 조회합니다.

    Args:
        query: 종목명(삼성전자), 6자리 티커(005930), 또는 지수(KOSPI, KOSDAQ)

    Returns:
        dict: 종목/지수 정보 + 한국어 요약
    """
    q = (query or "").strip()
    if not q:
        return {
            "ok": False,
            "error": "종목명(예: 삼성전자), 6자리 코드(예: 005930), 또는 지수(KOSPI/KOSDAQ)를 입력해주세요.",
        }

    # 지수 조회
    index_name = _is_index_query(q)
    if index_name:
        try:
            data = await _fetch_index_data(index_name)
            if not data.get("ok"):
                return data
            data["summary_ko"] = _index_summary(data)
            data["source"] = "polling.finance.naver.com"
            return data
        except Exception as e:
            return {"ok": False, "error": f"지수 조회 실패: {e}"}

    # 종목 조회: 티커 또는 이름 검색
    code = q if _is_ticker(q) else None
    market = ""
    candidates = []

    if code is None:
        try:
            search = await _search_stock(q)
            if not search.get("ok"):
                return search
            code = search["best"]["code"]
            market = search["best"].get("market", "")
            candidates = search.get("candidates", [])
        except Exception as e:
            return {"ok": False, "error": f"종목 검색 실패: {e}"}

    try:
        data = await _fetch_stock_data(code)
        if not data.get("ok"):
            return data
        data["summary_ko"] = _stock_summary(data, market)
        data["source"] = "polling.finance.naver.com"
        if candidates:
            data["candidates"] = candidates
        return data
    except Exception as e:
        return {"ok": False, "error": f"시세 조회 실패: {e}"}
