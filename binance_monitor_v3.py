#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安合约三维度评分监控系统 v3.0
结构分(35) + 资金分(25) + 技术(15) = 75分制
日线EMA5/EMA10反转 + 4h结构突破 + ADX_MA5状态机
"""

import requests
import pandas as pd
import numpy as np
import time
import sys
import os
from datetime import datetime, timedelta

# ============================================================
# CONFIG
# ============================================================

CONFIG = {
    "WATCHLIST": [
        "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","TRXUSDT","DOTUSDT",
        "AAPLUSDT","MSFTUSDT","GOOGLUSDT","AMZNUSDT","METAUSDT","NVDAUSDT","TSLAUSDT","NFLXUSDT","AMDUSDT","INTCUSDT",
        "ORCLUSDT","CSCOUSDT","IBMUSDT","CRMUSDT","NOWUSDT","DELLUSDT","HPEUSDT","SAMSUNGUSDT","SONYUSDT",
        "TSMUSDT","AVGOUSDT","QCOMUSDT","MUUSDT","ARMUSDT","WDCUSDT","SNDKUSDT","LITEUSDT","ASMLUSDT","LRCXUSDT",
        "KLACUSDT","AMATUSDT","SMCIUSDT","CIENUSDT","COHRUSDT","CRDOUSDT","MRVLUSDT","STXXUSDT","GLWUSDT","ASTSUSDT",
        "SKHYNIXUSDT","CRWDUSDT","VUSDT","JPMUSDT","BRKBUSDT","BXUSDT","HOODUSDT","COINUSDT","PAYPUSDT","CRCLUSDT",
        "AAOIUSDT","MSTRUSDT","BABAUSDT","WMTUSDT","HDUSDT","COSTUSDT","DISUSDT","UBERUSDT","EBAYUSDT","DKNGUSDT",
        "GMEUSDT","BBXUSDT","NOKUSDT","HYUNDAIUSDT","LLYUSDT","NVOUSDT","HIMSUSDT","USARUSDT","FLNCUSDT","BEUSDT",
        "ONDSUSDT","BMNRUSDT","PLTRUSDT","RKLBUSDT","SPCXUSDT","OPENAIUSDT","ANTHROPICUSDT","NBISUSDT","CBRSUSDT",
        "CRWVUSDT","QNTXUSDT","IRENUSDT","DRAMUSDT","SPYUSDT","QQQUSDT","IWMUSDT","SOXLUSDT","EWTUSDT","EWYUSDT",
        "EWJUSDT","EWZUSDT","XLEUSDT","URNMUSDT","UVXYUSDT","KORUUSDT","MVLLUSDT","TQQQUSDT","SQQQUSDT",
        "XAUUSDT","XAGUSDT","XPTUSDT","XPDUSDT","COPPERUSDT","CLUSDT","NATGASUSDT"
    ],
    "PRIMARY_INTERVAL": "4h", "SECONDARY_INTERVAL": "1h", "DAILY_INTERVAL": "1d",
    "PRIMARY_LOOKBACK": 100, "SECONDARY_LOOKBACK": 50, "DAILY_LOOKBACK": 30,
    "STRUCTURE_PERIOD": 10, "BREAKOUT_VOLUME_MULT": 1.5, "EMA21_DEVIATION": 0.02,
    "EMA_SHORT_DAILY": 5, "EMA_MID_DAILY": 10,
    "EMA_CROSS_GAP": 0.02, "BOTTOM_LOOKBACK": 10, "V_REVERSAL_THRESHOLD": 0.10,
    "ADX_TREND_THRESHOLD": 25, "ADX_NO_TREND": 18, "ADX_STRONG": 35,
    "ADX_CONFIRM_BARS": 3, "ADX_SLOPE_THRESHOLD": -3,
    "RSI_OVERSOLD": 40, "RSI_OVERBOUGHT": 75, "RSI_ENTRY_ZONE_LOW": 45, "RSI_ENTRY_ZONE_HIGH": 55,
    "FUNDING_EXTREME": 0.0005, "OI_CHANGE_THRESHOLD": 0.05, "VOLUME_SURGE": 3.0,
    "SCORE_ENTRY": 25, "SCORE_STRONG": 45, "SCORE_REVERSE": -25,
    "REQUEST_DELAY": 0.3, "MAX_RETRIES": 3, "TIMEOUT": 10,
    "BASE_URL": "https://fapi.binance.com"
}

WATCHLIST = CONFIG["WATCHLIST"]
BASE_URL = CONFIG["BASE_URL"]
KLINES_EP = "/fapi/v1/klines"
EXCHANGE_EP = "/fapi/v1/exchangeInfo"
TICKER_EP = "/fapi/v1/ticker/24hr"
FUNDING_EP = "/fapi/v1/premiumIndex"


def calc_rsi(close, period=14):
    d = close.diff()
    gain = d.where(d > 0, 0).rolling(period).mean()
    loss = (-d.where(d < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

def calc_sma(series, period):
    return series.rolling(period).mean()

def calc_bb(close, period=20, mult=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + std * mult, mid, mid - std * mult

def calc_adx(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    pdm = (high - high.shift(1)).clip(lower=0)
    ndm = (low.shift(1) - low).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0)
    ndm = ndm.where(ndm > pdm, 0)
    pdi = 100 * pdm.rolling(period).mean() / atr
    ndi = 100 * ndm.rolling(period).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    dx = dx.replace([np.inf, -np.inf], 0).fillna(0)
    return dx.rolling(period).mean(), pdi, ndi

def calc_vol_ma(vol, period=20):
    return vol.rolling(period).mean()

def fmt_price(p):
    if p >= 10000: return f"${p:,.0f}"
    elif p >= 100: return f"${p:,.2f}"
    elif p >= 1: return f"${p:.3f}"
    return f"${p:.6f}"

def fmt_pct(v):
    s = "+" if v >= 0 else ""
    return f"{s}{v*100:.1f}%"


# ============================================================
# DataCollector
# ============================================================

class DataCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.failures = {}
        self.valid_symbols = set()

    def _req(self, endpoint, params=None):
        url = f"{BASE_URL}{endpoint}"
        for attempt in range(1, CONFIG["MAX_RETRIES"] + 1):
            try:
                time.sleep(CONFIG["REQUEST_DELAY"])
                resp = self.session.get(url, params=params or {}, timeout=CONFIG["TIMEOUT"])
                if resp.status_code == 429:
                    time.sleep(2 ** attempt); continue
                if resp.status_code != 200:
                    if attempt < CONFIG["MAX_RETRIES"]: time.sleep(1); continue
                    return None
                return resp.json()
            except Exception:
                if attempt < CONFIG["MAX_RETRIES"]: time.sleep(1); continue
                return None
        return None

    def fetch_valid_symbols(self):
        """Get all PERPETUAL TRADING symbols from Binance"""
        data = self._req(EXCHANGE_EP)
        if data is None:
            print("Failed to fetch exchangeInfo, using default")
            return set(WATCHLIST)
        symbols = set()
        for s in data.get("symbols", []):
            if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING":
                symbols.add(s["symbol"])
        self.valid_symbols = symbols
        return symbols

    def get_klines(self, symbol, interval, limit):
        data = self._req(KLINES_EP, {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data is None or not isinstance(data, list) or len(data) == 0:
            return None
        df = pd.DataFrame(data, columns=['ot','o','h','l','c','v','ct','qv','n','tb','tbq','ig'])
        for col in ['o','h','l','c','v']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['ot'] = pd.to_datetime(df['ot'], unit='ms')
        return df

    def get_24h_ticker(self, symbol):
        return self._req(TICKER_EP, {'symbol': symbol})

    def get_funding(self, symbol):
        return self._req(FUNDING_EP, {'symbol': symbol})

    def is_delisted(self, symbol):
        self.failures[symbol] = self.failures.get(symbol, 0) + 1
        return self.failures[symbol] >= 3


# ============================================================
# ScoringEngine - 3维度评分系统
# ============================================================

class ScoringEngine:
    def __init__(self):
        pass

    def score_structure(self, df_4h, df_daily):
        """结构分: 0~35分"""
        score = 0
        notes = []
        close_4h = df_4h['c']
        vol_4h = df_4h['v']
        close_d = df_daily['c']
        ema5_d = calc_ema(close_d, CONFIG["EMA_SHORT_DAILY"])
        ema10_d = calc_ema(close_d, CONFIG["EMA_MID_DAILY"])
        ema21_4h = calc_ema(close_4h, 21)
        vol_ma_4h = calc_vol_ma(vol_4h, 20)

        c4 = close_4h.iloc[-1]
        recent_high = close_4h.iloc[-CONFIG["STRUCTURE_PERIOD"]:-1].max() if len(close_4h) > CONFIG["STRUCTURE_PERIOD"] else close_4h.max()
        vol_curr = vol_4h.iloc[-1]
        vol_avg = vol_ma_4h.iloc[-1] if not np.isnan(vol_ma_4h.iloc[-1]) else vol_curr

        # A. 趋势延续/突破
        breakout = c4 > recent_high and vol_curr > vol_avg * CONFIG["BREAKOUT_VOLUME_MULT"]
        pullback_ema21 = abs(c4 - ema21_4h.iloc[-1]) / c4 < CONFIG["EMA21_DEVIATION"] if c4 > 0 else False
        inside_range = c4 < recent_high and c4 > close_4h.iloc[-CONFIG["STRUCTURE_PERIOD"]:-1].min() if len(close_4h) > CONFIG["STRUCTURE_PERIOD"] else True
        breakdown = c4 < close_4h.iloc[-CONFIG["STRUCTURE_PERIOD"]:-1].min() if len(close_4h) > CONFIG["STRUCTURE_PERIOD"] else False

        if breakout and not pullback_ema21:
            score += 25; notes.append("4h突破前高+放量")
        elif breakout and pullback_ema21:
            score += 30; notes.append("4h突破+回踩EMA21")
        elif inside_range:
            score -= 20; notes.append("价格回到震荡区间")
        elif breakdown:
            score -= 15; notes.append("跌破前低")

        # B. 日线EMA5/EMA10反转
        ema5_val = ema5_d.iloc[-1] if not np.isnan(ema5_d.iloc[-1]) else close_d.iloc[-1]
        ema10_val = ema10_d.iloc[-1] if not np.isnan(ema10_d.iloc[-1]) else close_d.iloc[-1]
        ema5_prev = ema5_d.iloc[-2] if len(ema5_d) > 1 else ema5_val
        ema10_prev = ema10_d.iloc[-2] if len(ema10_d) > 1 else ema10_val

        golden_cross = ema5_val > ema10_val and ema5_prev <= ema10_prev
        death_cross = ema5_val < ema10_val and ema5_prev >= ema10_prev

        if golden_cross:
            stand = close_d.iloc[-1] > ema10_val
            volume_up = df_daily['v'].iloc[-1] > calc_vol_ma(df_daily['v'], 20).iloc[-1] * 1.2
            if stand and volume_up:
                score += 35; notes.append("EMA金叉+站稳+放量(强势)")
            else:
                score += 20; notes.append("EMA金叉")
        elif death_cross:
            score -= 15; notes.append("EMA死叉")
        elif abs(ema5_val - ema10_val) / ema10_val < CONFIG["EMA_CROSS_GAP"]:
            score += 20; notes.append("EMA接近+变盘即将确认")

        # V型反转检查
        price_change = (close_d.iloc[-1] - close_d.iloc[-5]) / close_d.iloc[-5] if len(close_d) > 5 and close_d.iloc[-5] > 0 else 0
        gap = abs(ema5_val - ema10_val) / ema10_val if ema10_val > 0 else 0
        if price_change > CONFIG["V_REVERSAL_THRESHOLD"] and gap > 0.05:
            notes.append("V型反弹,放弃追涨")

        # C. 日线结构确认
        daily_high_10 = close_d.iloc[-10:].max() if len(close_d) >= 10 else close_d.max()
        struct_confirm = close_d.iloc[-1] > daily_high_10 and df_daily['v'].iloc[-1] > calc_vol_ma(df_daily['v'], 20).iloc[-1] * 1.5 and close_d.iloc[-1] > ema10_val
        if struct_confirm:
            notes.append("日线结构确认")
        else:
            notes.append("日线未确认")

        return max(0, min(35, score)), " | ".join(notes) if notes else "-"

    def score_funding(self, funding_data, ticker_data, df_4h):
        """资金分: 0~25分"""
        score = 0
        notes = []

        funding_rate = funding_data.get('lastFundingRate', 0) if funding_data else 0
        try: funding_rate = float(funding_rate)
        except: funding_rate = 0
        extreme = CONFIG["FUNDING_EXTREME"]
        if funding_rate >= extreme:
            score -= 15; notes.append(f"资金费率{funding_rate*100:.3f}%(偏空)")
        elif funding_rate <= -extreme:
            score += 15; notes.append(f"资金费率{funding_rate*100:.3f}%(偏多)")
        else:
            notes.append(f"资金费率正常")

        if ticker_data and 'openInterest' in ticker_data:
            try:
                oi_now = float(ticker_data['openInterest'])
                price_change = float(ticker_data.get('priceChangePercent', 0)) / 100
                if price_change > 0 and oi_now > 0:
                    score += 15; notes.append("价格上涨+持仓增加")
                elif price_change > 0:
                    score -= 15; notes.append("价格上涨+持仓减少(危险)")
            except: pass

        vol_4h = df_4h['v']
        vol_ma = calc_vol_ma(vol_4h, 20)
        vol_ratio = vol_4h.iloc[-1] / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 0
        if vol_ratio >= CONFIG["VOLUME_SURGE"]:
            score += 10; notes.append(f"成交量{vol_ratio:.1f}x(放量)")
        elif vol_ratio >= 1.5:
            score += 5; notes.append(f"成交量{vol_ratio:.1f}x(温和)")

        return max(0, min(25, score)), " | ".join(notes) if notes else "-"

    def score_technical(self, df_4h):
        """技术分: 0~15分"""
        score = 0
        notes = []
        close = df_4h['c']
        high = df_4h['h']
        low = df_4h['l']

        adx, pdi, ndi = calc_adx(high, low, close, 14)
        adx_ma5 = calc_sma(adx, 5)
        rsi = calc_rsi(close, 14)

        adx_val = adx_ma5.iloc[-1] if not np.isnan(adx_ma5.iloc[-1]) else 0
        adx_hist = adx_ma5.tail(10).values

        if adx_val < CONFIG["ADX_NO_TREND"]:
            notes.append(f"ADX_MA5:{adx_val:.1f}(无趋势,0分)")
            return 0, " | ".join(notes)
        elif adx_val < CONFIG["ADX_TREND_THRESHOLD"]:
            notes.append(f"ADX_MA5:{adx_val:.1f}(过渡区,禁止信号)")
            return 0, " | ".join(notes)
        elif adx_val >= CONFIG["ADX_STRONG"]:
            score += 5; notes.append(f"ADX_MA5:{adx_val:.1f}(强趋势+5)")
        elif adx_val >= CONFIG["ADX_TREND_THRESHOLD"]:
            consecutive = sum(1 for v in adx_hist[-3:] if v >= CONFIG["ADX_TREND_THRESHOLD"])
            if consecutive >= CONFIG["ADX_CONFIRM_BARS"]:
                score += 5; notes.append(f"ADX_MA5:{adx_val:.1f}(趋势确认+5)")
            else:
                notes.append(f"ADX_MA5:{adx_val:.1f}(趋势未确认)")
                return 0, " | ".join(notes)

        pdi_val = pdi.iloc[-1] if not np.isnan(pdi.iloc[-1]) else 0
        ndi_val = ndi.iloc[-1] if not np.isnan(ndi.iloc[-1]) else 0
        if pdi_val > ndi_val and (pdi_val - ndi_val) > 5:
            score += 5; notes.append(f"+DI{pdi_val:.0f}>-DI{ndi_val:.0f}(+5)")
        elif ndi_val > pdi_val and (ndi_val - pdi_val) > 5:
            score -= 5; notes.append(f"-DI{ndi_val:.0f}>+DI{pdi_val:.0f}(-5)")

        rsi_val = rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50
        if CONFIG["RSI_OVERSOLD"] <= rsi_val <= 70:
            score += 5; notes.append(f"RSI:{rsi_val:.0f}(正常+5)")
        elif rsi_val > CONFIG["RSI_OVERBOUGHT"]:
            score -= 5; notes.append(f"RSI:{rsi_val:.0f}(超买-5)")

        return max(0, min(15, score)), " | ".join(notes) if notes else "-"


# ============================================================
# Analyzer - 主分析器
# ============================================================

class Analyzer:
    def __init__(self):
        self.scorer = ScoringEngine()

    def analyze(self, symbol, df_4h, df_1h, df_daily, funding_data, ticker_data):
        result = {'symbol': symbol}

        struct_score, struct_note = self.scorer.score_structure(df_4h, df_daily)
        funding_score, funding_note = self.scorer.score_funding(funding_data, ticker_data, df_4h)
        tech_score, tech_note = self.scorer.score_technical(df_4h)

        total = struct_score + funding_score + tech_score

        adx, pdi, ndi = calc_adx(df_4h['h'], df_4h['l'], df_4h['c'], 14)
        adx_ma5 = calc_sma(adx, 5)
        adx_val = adx_ma5.iloc[-1] if not np.isnan(adx_ma5.iloc[-1]) else 0

        if adx_val < CONFIG["ADX_NO_TREND"]:
            adx_status = "无趋势"
        elif adx_val < CONFIG["ADX_TREND_THRESHOLD"]:
            adx_status = "过渡区"
        elif adx_val >= CONFIG["ADX_STRONG"]:
            adx_status = "强趋势"
        else:
            consecutive = sum(1 for v in adx_ma5.tail(3) if v >= CONFIG["ADX_TREND_THRESHOLD"])
            adx_status = "趋势确认" if consecutive >= 3 else "趋势未确认"

        close_d = df_daily['c']
        ema5_d = calc_ema(close_d, CONFIG["EMA_SHORT_DAILY"])
        ema10_d = calc_ema(close_d, CONFIG["EMA_MID_DAILY"])
        ema5_val = ema5_d.iloc[-1] if not np.isnan(ema5_d.iloc[-1]) else close_d.iloc[-1]
        ema10_val = ema10_d.iloc[-1] if not np.isnan(ema10_d.iloc[-1]) else close_d.iloc[-1]
        ema5_prev = ema5_d.iloc[-2] if len(ema5_d) > 1 else ema5_val
        ema10_prev = ema10_d.iloc[-2] if len(ema10_d) > 1 else ema10_val

        golden_cross = ema5_val > ema10_val and ema5_prev <= ema10_prev
        death_cross = ema5_val < ema10_val and ema5_prev >= ema10_prev
        ema_status = "金叉" if golden_cross else "死叉" if death_cross else "金叉维持" if ema5_val > ema10_val else "死叉维持"

        daily_high_10 = close_d.iloc[-10:].max() if len(close_d) >= 10 else close_d.max()
        struct_confirm = close_d.iloc[-1] > daily_high_10 and close_d.iloc[-1] > ema10_val

        ema21_4h = calc_ema(df_4h['c'], 21).iloc[-1]
        rsi_val = calc_rsi(df_4h['c'], 14).iloc[-1]
        if np.isnan(rsi_val): rsi_val = 50

        pdi_val = pdi.iloc[-1] if not np.isnan(pdi.iloc[-1]) else 0
        ndi_val = ndi.iloc[-1] if not np.isnan(ndi.iloc[-1]) else 0

        funding_rate = 0
        if funding_data:
            try: funding_rate = float(funding_data.get('lastFundingRate', 0))
            except: pass

        price_24h = float(ticker_data.get('lastPrice', 0)) if ticker_data else df_1h['c'].iloc[-1]
        change_24h = float(ticker_data.get('priceChangePercent', 0)) / 100 if ticker_data else 0

        entry_signal = ""
        if total > CONFIG["SCORE_ENTRY"] and struct_confirm and adx_status in ("趋势确认", "强趋势"):
            deviation = abs(price_24h - ema21_4h) / ema21_4h if ema21_4h > 0 else 1
            if deviation < CONFIG["EMA21_DEVIATION"] and CONFIG["RSI_ENTRY_ZONE_LOW"] <= rsi_val <= CONFIG["RSI_ENTRY_ZONE_HIGH"]:
                entry_signal = "入场信号 | 轻仓试探"
            elif deviation >= CONFIG["EMA21_DEVIATION"]:
                entry_signal = "放弃等待"

        reversal_warnings = []
        adx_slope = adx_ma5.iloc[-1] - adx_ma5.iloc[-3] if len(adx_ma5) >= 3 else 0
        if adx_slope < CONFIG["ADX_SLOPE_THRESHOLD"]:
            reversal_warnings.append("ADX斜率下降")
        if close_d.iloc[-1] < ema10_val:
            reversal_warnings.append("跌破日线EMA10")
        if pdi_val < ndi_val and pdi.iloc[-2] > ndi.iloc[-2]:
            reversal_warnings.append("DI死叉")
        vol_now = df_4h['v'].iloc[-1]
        vol_ma = calc_vol_ma(df_4h['v'], 20).iloc[-1]
        if close_d.iloc[-1] < close_d.iloc[-2] and vol_now > vol_ma * 1.5:
            reversal_warnings.append("下跌放量")

        reversal_level = ""
        if len(reversal_warnings) >= 3:
            reversal_level = "趋势反转 | 清仓"
        elif len(reversal_warnings) >= 2:
            reversal_level = "变盘预警 | 减仓50%"

        result.update({
            'price': price_24h, 'change_24h': change_24h,
            'score_total': total, 'score_struct': struct_score,
            'score_funding': funding_score, 'score_tech': tech_score,
            'struct_note': struct_note, 'funding_note': funding_note,
            'tech_note': tech_note, 'adx_status': adx_status,
            'adx_val': adx_val, 'pdi': pdi_val, 'ndi': ndi_val,
            'rsi': rsi_val, 'ema5': ema5_val, 'ema10': ema10_val,
            'ema_status': ema_status, 'struct_confirm': struct_confirm,
            'ema21_4h': ema21_4h, 'funding_rate': funding_rate,
            'entry_signal': entry_signal,
            'reversal_warnings': reversal_warnings,
            'reversal_level': reversal_level,
        })
        return result


# ============================================================
# Output
# ============================================================

def fmt_signal(r):
    lines = []
    sym = r['symbol']
    price = fmt_price(r['price'])
    chg = fmt_pct(r['change_24h'])
    total = r['score_total']

    sig_emoji = ""
    if r['ema_status'] == "金叉":
        sig_emoji = "强势买入 | 正常仓位"
    elif "金叉" in r['ema_status']:
        sig_emoji = "金叉维持"
    elif r['ema_status'] == "死叉":
        sig_emoji = "死叉(偏空)"

    lines.append(f"{'='*56}")
    lines.append(f"[{sym}] | {price} | 24h {chg} | 总分:{total:+.0f}")
    lines.append(f"{'='*56}")
    lines.append(f"结构:{r['score_struct']:+d} | 资金:{r['score_funding']:+d} | 技术:{r['score_tech']:+d}")
    lines.append(f"日线: EMA5:{fmt_price(r['ema5'])} EMA10:{fmt_price(r['ema10'])}({r['ema_status']}) | 结构:{'确认' if r['struct_confirm'] else '未确认'}")
    lines.append(f"4h: ADX_MA5:{r['adx_val']:.1f}({r['adx_status']}) | +DI:{r['pdi']:.0f} -DI:{r['ndi']:.0f} | RSI:{r['rsi']:.0f}")
    lines.append(f"资金费率:{r['funding_rate']*100:.3f}%")

    if r['entry_signal']:
        lines.append(f"[{r['entry_signal']}]")
    if r['reversal_level']:
        lines.append(f"[!!! {r['reversal_level']}]")
    if r['reversal_warnings']:
        lines.append(f"预警: {', '.join(r['reversal_warnings'])}")

    lines.append(f"结构: {r['struct_note']}")
    lines.append(f"资金: {r['funding_note']}")
    lines.append(f"技术: {r['tech_note']}")

    if r['ema_status'] == "金叉" and r['struct_confirm']:
        lines.append("[建议: 等待回踩EMA21]")
        lines.append(f"止损: 4h EMA21 {fmt_price(r['ema21_4h'])}")
    elif r['ema_status'] == "死叉":
        lines.append("[建议: 观望或轻仓做空]")

    lines.append("")
    return "\n".join(lines)


def fmt_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = ["=" * 56, "币安合约三维度评分监控系统 v3.0", f"结构(35) + 资金(25) + 技术(15) = 75分制 | {now}", "=" * 56]
    return "\n".join(lines)


def fmt_footer(signal_count, elapsed):
    lines = ["=" * 56, f"完成 | 信号币种:{signal_count}个 | 耗时:{elapsed:.1f}秒", "=" * 56]
    return "\n".join(lines)


# ============================================================
# Main Monitor
# ============================================================

class BinanceMonitor:
    def __init__(self):
        self.collector = DataCollector()
        self.analyzer = Analyzer()
        self.valid_symbols = set()

    def run_once(self):
        start = time.time()
        all_results = []
        no_signal = []
        skipped = []
        errors = []

        print("正在获取币安合约列表...")
        self.valid_symbols = self.collector.fetch_valid_symbols()
        print(f"币安共有 {len(self.valid_symbols)} 个活跃永续合约\n")

        symbols_to_scan = []
        for sym in WATCHLIST:
            if sym in self.valid_symbols:
                symbols_to_scan.append(sym)
            else:
                skipped.append(sym)
                print(f"  {sym} 不在币安活跃合约列表,已跳过")

        print(f"\nWATCHLIST: {len(WATCHLIST)}个")
        print(f"有效合约: {len(symbols_to_scan)}个")
        print(f"跳过: {len(skipped)}个\n")

        print(fmt_header())
        print(f"\n开始扫描 {len(symbols_to_scan)} 个币种...")
        print(f"4h结构 + 日线EMA5/10 + ADX_MA5 + 资金费率\n")

        for i, sym in enumerate(symbols_to_scan, 1):
            print(f"  [{i:3d}/{len(symbols_to_scan)}] {sym:12s} ...", end=" ", flush=True)

            df_4h = self.collector.get_klines(sym, CONFIG["PRIMARY_INTERVAL"], CONFIG["PRIMARY_LOOKBACK"])
            if df_4h is None or len(df_4h) < 55:
                if self.collector.is_delisted(sym):
                    print("已下架")
                else:
                    print("数据异常")
                    errors.append(sym)
                continue

            df_1h = self.collector.get_klines(sym, CONFIG["SECONDARY_INTERVAL"], CONFIG["SECONDARY_LOOKBACK"])
            df_daily = self.collector.get_klines(sym, CONFIG["DAILY_INTERVAL"], CONFIG["DAILY_LOOKBACK"])
            funding = self.collector.get_funding(sym)
            ticker = self.collector.get_24h_ticker(sym)

            if df_daily is None or len(df_daily) < 15:
                print("日线不足")
                continue

            result = self.analyzer.analyze(sym, df_4h, df_1h, df_daily, funding, ticker)

            if result['score_total'] > CONFIG["SCORE_ENTRY"] or result['score_total'] < CONFIG["SCORE_REVERSE"]:
                all_results.append(result)
                tag = "BUY" if result['score_total'] > 0 else "SELL"
                print(f"{tag} 总分{result['score_total']:+.0f}")
            else:
                no_signal.append(sym)
                print(f"总分{result['score_total']:+.0f}")

        elapsed = time.time() - start
        all_results.sort(key=lambda x: x['score_total'], reverse=True)

        print(f"\n{'='*56}")
        strong_signals = [r for r in all_results if r['score_total'] > CONFIG["SCORE_ENTRY"]]
        reverse_signals = [r for r in all_results if r['score_total'] < CONFIG["SCORE_REVERSE"]]

        if strong_signals:
            print(f"强势信号: {len(strong_signals)}个 (总分>{CONFIG['SCORE_ENTRY']})")
            for r in strong_signals:
                print(fmt_signal(r))

        if reverse_signals:
            print(f"反转预警: {len(reverse_signals)}个 (总分<{CONFIG['SCORE_REVERSE']})")
            for r in reverse_signals:
                print(fmt_signal(r))

        if no_signal:
            print(f"\n无显著信号 ({len(no_signal)}个): {', '.join(no_signal[:15])}")
            if len(no_signal) > 15:
                print(f"  ...等共{len(no_signal)}个")

        if errors:
            print(f"\n数据异常: {', '.join(errors[:5])}")

        print(fmt_footer(len(all_results), elapsed))
        return all_results

    def run_continuous(self):
        print("\n" + "=" * 56)
        print("币安三维度评分监控系统启动")
        print("结构(35) + 资金(25) + 技术(15) = 75分制")
        print("每1小时自动扫描 | Ctrl+C 停止")
        print("=" * 56 + "\n")
        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    print(f"\n扫描出错: {str(e)[:100]}")
                    print("10分钟后重试...")
                    time.sleep(600)
                    continue
                now = datetime.now()
                next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait = (next_run - now).total_seconds()
                if wait > 0:
                    print(f"\n休眠{int(wait/60)}分钟...")
                    time.sleep(wait)
        except KeyboardInterrupt:
            print("\n\n已停止")
            sys.exit(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='币安合约三维度评分监控系统 v3.0')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    parser.add_argument('--symbol', type=str, help='只分析指定币种')
    args = parser.parse_args()
    monitor = BinanceMonitor()

    if args.symbol:
        print(f"单独分析: {args.symbol}")
        monitor.valid_symbols = monitor.collector.fetch_valid_symbols()
        if args.symbol not in monitor.valid_symbols:
            print(f"{args.symbol} 不在币安活跃合约列表")
            return
        df_4h = monitor.collector.get_klines(args.symbol, CONFIG["PRIMARY_INTERVAL"], CONFIG["PRIMARY_LOOKBACK"])
        df_1h = monitor.collector.get_klines(args.symbol, CONFIG["SECONDARY_INTERVAL"], CONFIG["SECONDARY_LOOKBACK"])
        df_daily = monitor.collector.get_klines(args.symbol, CONFIG["DAILY_INTERVAL"], CONFIG["DAILY_LOOKBACK"])
        funding = monitor.collector.get_funding(args.symbol)
        ticker = monitor.collector.get_24h_ticker(args.symbol)
        if df_4h is not None and df_daily is not None:
            r = monitor.analyzer.analyze(args.symbol, df_4h, df_1h, df_daily, funding, ticker)
            print(fmt_signal(r))
        else:
            print("数据获取失败")
    elif args.once:
        monitor.run_once()
    else:
        monitor.run_continuous()


if __name__ == "__main__":
    main()
