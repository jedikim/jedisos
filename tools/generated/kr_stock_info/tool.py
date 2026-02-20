from jedisos.forge.decorator import tool
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx

_AC_URL = "https://ac.stock.naver.com/ac"
_POLLING_URL = "https://polling.finance.naver.com/api/realtime"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JediSOS/1.0)"}

def _safe_float(v: Any) -> Optional[float]:
    if v is None: return None
    try: return float(v)
    except (ValueError, TypeError): return None

def _safe_int(v: Any) -> Optional[int]:
    if v is None: return None
    try: return int(float(v))
    except (ValueError, TypeError): return None

def _format_int(v: Optional[int]) -> str:
    return f"{v:,}" if v is not None else "정보 없음"

def _format_price_krw(v: Optional[float]) -> str:
    if v is None: return "정보 없음"
    try: return f"{int(abs(v)):,}원"
    except Exception: return "정보 없음"

def _format_percent(v: Optional[float], digits: int = 2) -> str:
    if v is None: return "정보 없음"
    try: return f"{abs(v):.{digits}f}%"
    except Exception: return "정보 없음"

def _format_index_value(v: Optional[float]) -> str:
    if v is None: return "정보 없음"
    try: return f"{abs(v) / 100:,.2f}"
    except Exception: return "정보 없음"

def _is_ticker(q: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", q.strip()))

def _is_index_query(q: str) -> Optional[str]:
    t = q.strip().upper().replace(" ", "")
    mapping = {"KOSPI": "KOSPI", "코스피": "KOSPI", "KOSPI지수": "KOSPI", "코스피지수": "KOSPI", "KOSDAQ": "KOSDAQ", "코스닥": "KOSDAQ", "KOSDAQ지수": "KOSDAQ", "코스닥지수": "KOSDAQ"}
    return mapping.get(t)

def _change_sign(rf: str) -> str:
    return {"1": "+", "2": "+", "3": "", "4": "-", "5": "-"}.get(rf, "")

def _format_market_cap_kr(v: Optional[int]) -> str:
    if v is None or v <= 0: return "정보 없음"
    eok, jo = 100_000_000, 1_000_000_000_000
    jo_part, rem = v // jo, v % jo
    eok_part = rem // eok
    if jo_part > 0:
        return f"{jo_part}조 {eok_part:,}억" if eok_part > 0 else f"{jo_part}조"
    return f"{eok_part:,}억" if eok_part > 0 else "정보 없음"

def _format_per_bae(v: Optional[float]) -> str:
    if v is None or v <= 0: return "정보 없음"
    return f"{v:.1f}배"

def _format_ymd(date_str: Optional[str]) -> Optional[str]:
    if not date_str: return None
    s = str(date_str).strip()
    if re.fullmatch(r"\d{8}", s): return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s): return s
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", s): return s.replace(".", "-")
    return s

async def _search_stock(query: str) -> Dict[str, Any]:
    params = {"q": query, "target": "stock"}
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(_AC_URL, params=params)
        r.raise_for_status()
        data = r.json()
    items = data.get("items") or []
    if not items: return {"ok": False, "error": f"'{query}' 종목을 찾지 못했습니다.", "candidates": []}
    candidates = [{"code": i.get("code"), "name": i.get("name"), "market": i.get("typeName", "")} for i in items[:5]]
    return {"ok": True, "best": candidates[0], "candidates": candidates}

async def _fetch_realtime(query_expr: str) -> Dict[str, Any]:
    url = f"{_POLLING_URL}?query={quote(query_expr)}"
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(url)
        r.raise_for_status()
        return json.loads(r.content.decode("euc-kr", errors="replace"))

def _extract_first_data(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    areas = (payload.get("result") or {}).get("areas") or []
    if not areas: return None
    datas = areas[0].get("datas") or []
    if not datas: return None
    return datas[0] if isinstance(datas[0], dict) else None

def _extract_52w_from_raw(d: Dict[str, Any]) -> Dict[str, Any]:
    def pick_float(keys: List[str]) -> Optional[float]:
        for k in keys:
            v = _safe_float(d.get(k))
            if v is not None and v != 0: return v
        return None
    def pick_date(keys: List[str]) -> Optional[str]:
        for k in keys:
            v = d.get(k)
            norm = _format_ymd(v if v is not None else None)
            if norm: return norm
        return None
    high = pick_float(["h52", "h52w", "w52High", "high52", "high52w", "h52p", "h52P", "h52v", "h52V"])
    low = pick_float(["l52", "l52w", "w52Low", "low52", "low52w", "l52p", "l52P", "l52v", "l52V"])
    high_date = pick_date(["h52d", "h52D", "h52Date", "w52HighDate", "high52Date", "high52d"])
    low_date = pick_date(["l52d", "l52D", "l52Date", "w52LowDate", "low52Date", "low52d"])
    out = {}
    if high is not None: out["week52_high"] = high
    if low is not None: out["week52_low"] = low
    if high_date: out["week52_high_date"] = high_date
    if low_date: out["week52_low_date"] = low_date
    return out

async def _fetch_stock_data(code: str) -> Dict[str, Any]:
    payload = await _fetch_realtime(f"SERVICE_ITEM:{code}")
    d = _extract_first_data(payload)
    if not d: return {"ok": False, "error": "시세 데이터를 받지 못했습니다."}
    sign = _change_sign(str(d.get("rf", "")))
    cv, nv = _safe_float(d.get("cv")), _safe_float(d.get("nv"))
    eps, bps = _safe_float(d.get("eps")), _safe_float(d.get("bps"))
    per, pbr = _safe_float(d.get("per")), _safe_float(d.get("pbr"))
    if per is None and nv is not None and eps is not None and eps > 0: per = round(nv / eps, 2)
    if pbr is None and nv is not None and bps is not None and bps > 0: pbr = round(nv / bps, 2)
    market_cap = _safe_int(d.get("mktCap")) or _safe_int(d.get("mkp")) or _safe_int(d.get("mcp")) or _safe_int(d.get("marketCap")) or _safe_int(d.get("st"))
    week52 = _extract_52w_from_raw(d)
    return {
        "ok": True, "code": d.get("cd"), "name": d.get("nm"), "price": nv, "change": cv, "change_sign": sign,
        "change_rate": _safe_float(d.get("cr")), "open": _safe_float(d.get("ov")), "high": _safe_float(d.get("hv")),
        "low": _safe_float(d.get("lv")), "volume": _safe_float(d.get("aq")), "trade_amount": _safe_float(d.get("aa")),
        "prev_close": _safe_float(d.get("pcv") or d.get("sv")), "upper_limit": _safe_float(d.get("ul")),
        "lower_limit": _safe_float(d.get("ll")), "eps": eps, "bps": bps, "per": per, "pbr": pbr,
        "dividend": _safe_float(d.get("dv")), "market_cap": market_cap, "market_status": d.get("ms"),
        "week52_high": week52.get("week52_high"), "week52_low": week52.get("week52_low"),
        "week52_high_date": week52.get("week52_high_date"), "week52_low_date": week52.get("week52_low_date"),
        "raw": d
    }

async def _fetch_index_data(index: str) -> Dict[str, Any]:
    payload = await _fetch_realtime(f"SERVICE_INDEX:{index}")
    d = _extract_first_data(payload)
    if not d: return {"ok": False, "error": "지수 데이터를 받지 못했습니다."}
    sign = _change_sign(str(d.get("rf", "")))
    week52 = _extract_52w_from_raw(d)
    out = {
        "ok": True, "index": d.get("cd"), "value": _safe_float(d.get("nv")), "change": _safe_float(d.get("cv")),
        "change_sign": sign, "change_rate": _safe_float(d.get("cr")), "volume": _safe_float(d.get("aq")),
        "trade_amount": _safe_float(d.get("aa")), "market_status": d.get("ms"), "raw": d
    }
    out.update(week52)
    return out

def _format_52w_line(data: Dict[str, Any]) -> str:
    hi, lo = _safe_float(data.get("week52_high")), _safe_float(data.get("week52_low"))
    hi_d, lo_d = _format_ymd(data.get("week52_high_date")), _format_ymd(data.get("week52_low_date"))
    if hi is None and lo is None: return "52주 최고가/최저가 정보 없음"
    def with_date(price: Optional[float], d: Optional[str]) -> str:
        p = _format_price_krw(price)
        if p == "정보 없음": return "정보 없음"
        return f"{p}({d})" if d else p
    return f"52주 최고가 {with_date(hi, hi_d)} / 52주 최저가 {with_date(lo, lo_d)}"

def _stock_summary_one_line(data: Dict[str, Any], market: str = "") -> str:
    name, code = data.get("name") or "?", data.get("code") or ""
    header = f"{name}({code}) [{market}]" if market else f"{name}({code})"
    sign = data.get("change_sign") or ""
    change_krw = _format_price_krw(data.get("change"))
    change_part = f"{sign}{change_krw.replace('원', '')}원" if change_krw != "정보 없음" and sign else change_krw
    rate_txt = _format_percent(data.get("change_rate"))
    rate_part = f"{sign}{rate_txt}" if rate_txt != "정보 없음" and sign else rate_txt
    parts = [
        header, f"현재가 {_format_price_krw(data.get('price'))}", f"등락 {change_part} / {rate_part}",
        f"거래량 {_format_int(_safe_int(data.get('volume')))}", f"시가총액 {_format_market_cap_kr(_safe_int(data.get('market_cap')))}",
        f"PER {_format_per_bae(_safe_float(data.get('per')))}", _format_52w_line(data)
    ]
    return " | ".join(parts)

def _index_summary_one_line(data: Dict[str, Any]) -> str:
    index = data.get("index") or "?"
    value = _format_index_value(data.get("value"))
    sign = data.get("change_sign") or ""
    change = _format_index_value(data.get("change"))
    change_part = f"{sign}{change}p" if change != "정보 없음" and sign else (f"{change}p" if change != "정보 없음" else "정보 없음")
    rate_txt = _format_percent(data.get("change_rate"))
    rate_part = f"{sign}{rate_txt}" if rate_txt != "정보 없음" and sign else rate_txt
    parts = [
        f"{index} {value}", f"등락 {change_part} / {rate_part}", f"거래량 {_format_int(_safe_int(data.get('volume')))}",
        "시가총액 정보 없음", "PER 정보 없음"
    ]
    if _safe_float(data.get("week52_high")) is not None or _safe_float(data.get("week52_low")) is not None:
        parts.append(_format_52w_line(data))
    return " | ".join(parts)

@tool(name="kr_stock_info", description="한국 주식(KOSPI/KOSDAQ) 종목명(삼성전자) 또는 6자리 티커(005930)로 실시간 현재가/등락/거래량/시가총액/PER 및 52주 최고가/최저가(가능 시 날짜 포함)를 조회합니다. 'KOSPI 지수', 'KOSDAQ 지수'도 조회 가능합니다.")
async def kr_stock_info(query: str) -> dict:
    q = (query or "").strip()
    if not q:
        return {"ok": True, "type": "help", "summary_ko": "입력 예: '삼성전자', '005930', 'KOSPI 지수', 'KOSDAQ 지수'", "message": "종목명(예: 삼성전자), 6자리 코드(예: 005930), 또는 지수(KOSPI/KOSDAQ)를 입력해주세요."}
    index_name = _is_index_query(q)
    if index_name:
        try:
            data = await _fetch_index_data(index_name)
            if not data.get("ok"): return data
            data["type"] = "index"
            data["summary_ko"] = _index_summary_one_line(data)
            data["source"] = "polling.finance.naver.com"
            return data
        except Exception as e:
            return {"ok": False, "error": f"지수 조회 실패: {e}"}
    code = q if _is_ticker(q) else None
    market, candidates = "", []
    if code is None:
        try:
            search = await _search_stock(q)
            if not search.get("ok"): return search
            code = (search.get("best") or {}).get("code")
            market = (search.get("best") or {}).get("market", "")
            candidates = search.get("candidates", []) or []
            if not code: return {"ok": False, "error": "종목 코드를 확인하지 못했습니다."}
        except Exception as e:
            return {"ok": False, "error": f"종목 검색 실패: {e}"}
    try:
        data = await _fetch_stock_data(code)
        if not data.get("ok"): return data
        data["type"] = "stock"
        data["summary_ko"] = _stock_summary_one_line(data, market)
        data["source"] = "polling.finance.naver.com"
        data["market_cap_ko"] = _format_market_cap_kr(_safe_int(data.get("market_cap")))
        data["per_ko"] = _format_per_bae(_safe_float(data.get("per")))
        data["week52_ko"] = _format_52w_line(data)
        if candidates: data["candidates"] = candidates
        return data
    except Exception as e:
        return {"ok": False, "error": f"시세 조회 실패: {e}"}
