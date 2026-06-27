#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安合约专业分析监控系统 v4.0
日线定趋势 / 4H共振 / 15M买卖点
专业文字描述，无分数，像分析师报告
"""

import requests
import pandas as pd
import numpy as np
import time
import sys
from datetime import datetime, timedelta

# ============================================================
# CONFIG
# ============================================================

CONFIG = {
    "WATCHLIST": [
        "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","TRXUSDT","DOTUSDT",
        "LINKUSDT","MATICUSDT","LTCUSDT","BCHUSDT","ETCUSDT","FILUSDT","ATOMUSDT","ARBUSDT","OPUSDT","APTUSDT",
        "SUIUSDT","SEIUSDT","TIAUSDT","NEARUSDT","ALGOUSDT","ICPUSDT","VETUSDT","FLOWUSDT","EOSUSDT","XTZUSDT",
        "THETAUSDT","XLMUSDT","HBARUSDT","FTMUSDT","GRTUSDT","MANAUSDT","SANDUSDT","AXSUSDT","CHZUSDT","APEUSDT",
        "UNIUSDT","AAVEUSDT","MKRUSDT","CRVUSDT","SUSHIUSDT","COMPUSDT","SNXUSDT","YFIUSDT","1INCHUSDT","DYDXUSDT",
        "INJUSDT","RUNEUSDT","IMXUSDT","LDOUSDT","RNDRUSDT","ENSUSDT","ZILUSDT","KAVAUSDT","ROSEUSDT","GMTUSDT",
        "GALAUSDT","ENJUSDT","BATUSDT","DASHUSDT","ZECUSDT","XMRUSDT","IOTAUSDT","QTUMUSDT","ONTUSDT","NEOUSDT",
        "BANDUSDT","KSMUSDT","WAVESUSDT","RVNUSDT","ICXUSDT","STORJUSDT","SFPUSDT","COTIUSDT","ANKRUSDT","SKLUSDT",
        "RLCUSDT","NKNUSDT","DGBUSDT","IOSTUSDT","ZRXUSDT"
    ],
    "TF_DAILY": "1d", "TF_4H": "4h", "TF_15M": "15m",
    "LOOKBACK_DAILY": 90, "LOOKBACK_4H": 100, "LOOKBACK_15M": 100,
    "REQUEST_DELAY": 0.3, "MAX_RETRIES": 3, "TIMEOUT": 10,
    "BASE_URL": "https://fapi.binance.com",
    "ADX_TREND": 25, "ADX_NO_TREND": 18, "ADX_STRONG": 35,
    "RSI_LOW": 30, "RSI_HIGH": 70, "SCORE_MIN": 30
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
    if pd.isna(p): return "$N/A"
    if p >= 10000: return f"${p:,.0f}"
    elif p >= 100: return f"${p:,.2f}"
    elif p >= 1: return f"${p:.3f}"
    elif p > 0: return f"${p:.6f}"
    return "$N/A"

def fmt_pct(v):
    if pd.isna(v): return "N/A%"
    s = "+" if v >= 0 else ""
    return f"{s}{v*100:.2f}%"


CATEGORY_MAP = {
    "BTCUSDT":"加密货币","ETHUSDT":"加密货币","SOLUSDT":"加密货币","BNBUSDT":"加密货币","XRPUSDT":"加密货币",
    "DOGEUSDT":"加密货币","ADAUSDT":"加密货币","AVAXUSDT":"加密货币","TRXUSDT":"加密货币","DOTUSDT":"加密货币",
    "LINKUSDT":"加密货币","MATICUSDT":"加密货币","LTCUSDT":"加密货币","BCHUSDT":"加密货币","ETCUSDT":"加密货币",
    "FILUSDT":"加密货币","ATOMUSDT":"加密货币","ARBUSDT":"加密货币","OPUSDT":"加密货币","APTUSDT":"加密货币",
    "SUIUSDT":"加密货币","SEIUSDT":"加密货币","TIAUSDT":"加密货币","NEARUSDT":"加密货币","ALGOUSDT":"加密货币",
    "ICPUSDT":"加密货币","VETUSDT":"加密货币","FLOWUSDT":"加密货币","EOSUSDT":"加密货币","XTZUSDT":"加密货币",
    "THETAUSDT":"加密货币","XLMUSDT":"加密货币","HBARUSDT":"加密货币","FTMUSDT":"加密货币","GRTUSDT":"加密货币",
    "MANAUSDT":"加密货币","SANDUSDT":"加密货币","AXSUSDT":"加密货币","CHZUSDT":"加密货币","APEUSDT":"加密货币",
    "UNIUSDT":"加密货币","AAVEUSDT":"加密货币","MKRUSDT":"加密货币","CRVUSDT":"加密货币","SUSHIUSDT":"加密货币",
    "COMPUSDT":"加密货币","SNXUSDT":"加密货币","YFIUSDT":"加密货币","1INCHUSDT":"加密货币","DYDXUSDT":"加密货币",
    "INJUSDT":"加密货币","RUNEUSDT":"加密货币","IMXUSDT":"加密货币","LDOUSDT":"加密货币","RNDRUSDT":"加密货币",
    "ENSUSDT":"加密货币","ZILUSDT":"加密货币","KAVAUSDT":"加密货币","ROSEUSDT":"加密货币","GMTUSDT":"加密货币",
    "GALAUSDT":"加密货币","ENJUSDT":"加密货币","BATUSDT":"加密货币","DASHUSDT":"加密货币","ZECUSDT":"加密货币",
    "XMRUSDT":"加密货币","IOTAUSDT":"加密货币","QTUMUSDT":"加密货币","ONTUSDT":"加密货币","NEOUSDT":"加密货币",
    "BANDUSDT":"加密货币","KSMUSDT":"加密货币","WAVESUSDT":"加密货币","RVNUSDT":"加密货币","ICXUSDT":"加密货币",
    "STORJUSDT":"加密货币","SFPUSDT":"加密货币","COTIUSDT":"加密货币","ANKRUSDT":"加密货币","SKLUSDT":"加密货币",
    "RLCUSDT":"加密货币","NKNUSDT":"加密货币","DGBUSDT":"加密货币","IOSTUSDT":"加密货币","ZRXUSDT":"加密货币"
}


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
        data = self._req(EXCHANGE_EP)
        if data is None:
            print("获取合约列表失败，使用默认列表")
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
# Analyzer
# ============================================================

class Analyzer:
    def analyze(self, symbol, df_4h, df_1h, df_daily, funding_data, ticker_data):
        result = {'symbol': symbol}

        close_d = df_daily['c']
        close_4h = df_4h['c']
        close_1h = df_1h['c'] if df_1h is not None else df_4h['c']
        high_4h = df_4h['h']
        low_4h = df_4h['l']
        vol_4h = df_4h['v']

        ema5_d = calc_ema(close_d, 5)
        ema10_d = calc_ema(close_d, 10)
        ema21_4h = calc_ema(close_4h, 21)
        adx, pdi, ndi = calc_adx(high_4h, low_4h, close_4h, 14)
        adx_ma5 = calc_sma(adx, 5)
        rsi = calc_rsi(close_4h, 14)
        vol_ma_4h = calc_vol_ma(vol_4h, 20)

        c_d = close_d.iloc[-1]
        c_1h = close_1h.iloc[-1]
        c_1h_prev = close_1h.iloc[-2] if len(close_1h) > 1 else c_1h
        c_4h_prev = close_4h.iloc[-2] if len(close_4h) > 1 else close_4h.iloc[-1]
        c_d_prev = close_d.iloc[-2] if len(close_d) > 1 else c_d

        ema5_val = ema5_d.iloc[-1] if not pd.isna(ema5_d.iloc[-1]) else c_d
        ema10_val = ema10_d.iloc[-1] if not pd.isna(ema10_d.iloc[-1]) else c_d
        ema5_prev = ema5_d.iloc[-2] if len(ema5_d) > 1 else ema5_val
        ema10_prev = ema10_d.iloc[-2] if len(ema10_d) > 1 else ema10_val
        ema21_val = ema21_4h.iloc[-1] if not pd.isna(ema21_4h.iloc[-1]) else close_4h.iloc[-1]

        adx_val = adx_ma5.iloc[-1] if not pd.isna(adx_ma5.iloc[-1]) else 0
        pdi_val = pdi.iloc[-1] if not pd.isnan(pdi.iloc[-1]) else 0
        ndi_val = ndi.iloc[-1] if not pd.isnan(ndi.iloc[-1]) else 0
        rsi_val = rsi.iloc[-1] if not pd.isnan(rsi.iloc[-1]) else 50
        vol_now = vol_4h.iloc[-1]
        vol_avg = vol_ma_4h.iloc[-1] if not pd.isna(vol_ma_4h.iloc[-1]) else vol_now
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        price_24h = float(ticker_data.get('lastPrice', close_4h.iloc[-1])) if ticker_data else close_4h.iloc[-1]
        change_24h = float(ticker_data.get('priceChangePercent', 0)) / 100 if ticker_data else 0
        change_1h = (c_1h - c_1h_prev) / c_1h_prev if c_1h_prev > 0 else 0
        change_4h = (close_4h.iloc[-1] - c_4h_prev) / c_4h_prev if c_4h_prev > 0 else 0

        funding_rate = 0
        if funding_data:
            try: funding_rate = float(funding_data.get('lastFundingRate', 0))
            except: pass

        category = CATEGORY_MAP.get(symbol, "加密货币")

        # 日线结构
        golden_cross = ema5_val > ema10_val and ema5_prev <= ema10_prev
        death_cross = ema5_val < ema10_val and ema5_prev >= ema10_prev
        ema_gap = abs(ema5_val - ema10_val) / ema10_val if ema10_val > 0 else 0
        price_above_ema10 = c_d > ema10_val
        daily_high_10 = close_d.iloc[-10:].max() if len(close_d) >= 10 else close_d.max()
        struct_confirm = c_d > daily_high_10 and c_d > ema10_val

        if golden_cross:
            daily_struct = f"日线出现金叉信号，EMA5({fmt_price(ema5_val)})刚刚上穿EMA10({fmt_price(ema10_val)})，底部反转形态确认中"
        elif death_cross:
            daily_struct = f"日线死叉，EMA5({fmt_price(ema5_val)})在EMA10({fmt_price(ema10_val)})下方，处于下降趋势"
        elif ema5_val > ema10_val and price_above_ema10:
            if ema_gap < 0.02:
                daily_struct = f"日线上升趋势维持，EMA5({fmt_price(ema5_val)})在EMA10({fmt_price(ema10_val)})上方但差距很小，趋势稳定"
            else:
                daily_struct = f"日线处于上升趋势，EMA5({fmt_price(ema5_val)})在EMA10({fmt_price(ema10_val)})上方，价格站稳EMA10之上"
        elif ema5_val < ema10_val and not price_above_ema10:
            daily_struct = f"日线处于下降趋势，EMA5({fmt_price(ema5_val)})在EMA10({fmt_price(ema10_val)})下方，价格低于EMA10"
        else:
            daily_struct = f"日线处于震荡整理，EMA5({fmt_price(ema5_val)})与EMA10({fmt_price(ema10_val)})纠缠，方向不明"

        if struct_confirm:
            daily_struct += "，日线结构已确认（突破近10日高点）"
        else:
            daily_struct += "，日线结构尚未确认"

        # 4H趋势
        adx_slope = adx_ma5.iloc[-1] - adx_ma5.iloc[-3] if len(adx_ma5) >= 3 else 0
        di_cross = pdi_val < ndi_val and (pdi.iloc[-2] if len(pdi) > 1 else pdi_val) >= (ndi.iloc[-2] if len(ndi) > 1 else ndi_val)

        if adx_val < CONFIG["ADX_NO_TREND"]:
            h4_trend = f"4小时无趋势，ADX_MA5处于{adx_val:.1f}（低于18），市场处于震荡阶段，多空方向不明"
        elif adx_val < CONFIG["ADX_TREND"]:
            h4_trend = f"4小时处于过渡区，ADX_MA5为{adx_val:.1f}（18-25之间），趋势尚未明确形成，建议观望等待"
        elif adx_val >= CONFIG["ADX_STRONG"]:
            h4_trend = f"4小时强趋势，ADX_MA5达到{adx_val:.1f}（高于35），趋势强劲但需警惕过热反转"
            if adx_slope < -3:
                h4_trend += f"，ADX斜率下降({adx_slope:.1f})，趋势强度可能正在减弱"
        else:
            h4_trend = f"4小时趋势确认，ADX_MA5为{adx_val:.1f}（趋势区），+DI({pdi_val:.0f})与-DI({ndi_val:.0f})"
            if pdi_val > ndi_val: h4_trend += "，多头占据优势"
            elif ndi_val > pdi_val: h4_trend += "，空头占据优势"
            if di_cross: h4_trend += "，刚刚发生DI死叉，趋势可能反转"

        # 资金状态
        if funding_rate >= 0.0008:
            funding_desc = f"资金费率极高（{funding_rate*100:.3f}%），多头严重过热，拥挤度高，回调风险极大"
        elif funding_rate >= 0.0005:
            funding_desc = f"资金费率偏高（{funding_rate*100:.3f}%），多头情绪过热，注意回调风险"
        elif funding_rate <= -0.0008:
            funding_desc = f"资金费率极低（{funding_rate*100:.3f}%），空头极度拥挤，可能反弹"
        elif funding_rate <= -0.0005:
            funding_desc = f"资金费率偏低（{funding_rate*100:.3f}%），空头情绪浓厚"
        else:
            funding_desc = f"资金费率正常（{funding_rate*100:.3f}%），多空力量相对平衡"

        if vol_ratio >= 3: funding_desc += f"，成交量大幅放大（{vol_ratio:.1f}倍均量），资金活跃度高"
        elif vol_ratio >= 1.5: funding_desc += f"，成交量温和放大（{vol_ratio:.1f}倍均量）"
        else: funding_desc += f"，成交量萎缩（{vol_ratio:.1f}倍均量），资金参与度低"

        # 技术状态
        if rsi_val <= CONFIG["RSI_LOW"]:
            tech_desc = f"RSI处于{rsi_val:.0f}（超卖区），短期下跌过度，反弹概率增加"
        elif rsi_val >= CONFIG["RSI_HIGH"]:
            tech_desc = f"RSI处于{rsi_val:.0f}（超买区），短期上涨过度，回调概率增加"
        elif rsi_val >= 55: tech_desc = f"RSI处于{rsi_val:.0f}（偏强区），动能健康偏强"
        elif rsi_val <= 45: tech_desc = f"RSI处于{rsi_val:.0f}（偏弱区），动能偏弱但未到超卖"
        else: tech_desc = f"RSI处于{rsi_val:.0f}（中性区），动能平衡"

        if adx_val >= CONFIG["ADX_TREND"]: tech_desc += f"，ADX趋势强度足够({adx_val:.1f})，趋势可持续"
        elif adx_val >= CONFIG["ADX_NO_TREND"]: tech_desc += f"，ADX处于过渡区({adx_val:.1f})，趋势方向待确认"
        else: tech_desc += f"，ADX低于18({adx_val:.1f})，无趋势行情"

        # 背离
        recent_high_idx = close_4h.iloc[-20:].idxmax() if len(close_4h) >= 20 else close_4h.idxmax()
        price_at_high = close_4h.loc[recent_high_idx] if recent_high_idx in close_4h.index else close_4h.iloc[-1]
        rsi_at_high = rsi.loc[recent_high_idx] if recent_high_idx in rsi.index else rsi.iloc[-1]
        if close_4h.iloc[-1] > price_at_high * 0.98 and rsi_val < rsi_at_high - 10 and rsi_val > 50:
            tech_desc += "，出现顶背离信号（价格接近前高但RSI未跟上），动能衰竭"
        elif close_4h.iloc[-1] < price_at_high * 0.95 and rsi_val > CONFIG["RSI_LOW"] and adx_slope < -3:
            tech_desc += "，出现底背离迹象（价格下跌但RSI未创新低）"

        # 综合评分（内部用，不显示）
        score = 0
        if golden_cross: score += 35
        elif ema5_val > ema10_val and price_above_ema10: score += 25
        elif death_cross: score -= 15
        if adx_val >= CONFIG["ADX_TREND"] and pdi_val > ndi_val: score += 20
        elif adx_val >= CONFIG["ADX_STRONG"]: score += 25
        elif adx_val < CONFIG["ADX_NO_TREND"]: score -= 10
        if funding_rate <= -0.0005: score += 10
        elif funding_rate >= 0.0005: score -= 10
        if vol_ratio >= 3: score += 10
        elif vol_ratio >= 1.5: score += 5
        if CONFIG["RSI_LOW"] <= rsi_val <= 70: score += 5
        elif rsi_val > CONFIG["RSI_HIGH"]: score -= 5
        if di_cross: score -= 15

        # 变盘预警
        reversal_count = 0; reversal_items = []
        if adx_slope < -3: reversal_count += 1; reversal_items.append("ADX斜率快速下降")
        if c_d < ema10_val: reversal_count += 1; reversal_items.append("价格跌破日线EMA10")
        if di_cross: reversal_count += 1; reversal_items.append("+DI与-DI死叉")
        if c_d < c_d_prev and vol_now > vol_avg * 1.5: reversal_count += 1; reversal_items.append("下跌放量")

        reversal_warning = ""
        if reversal_count >= 3: reversal_warning = f"趋势反转 | 清仓 ({', '.join(reversal_items)})"
        elif reversal_count >= 2: reversal_warning = f"变盘预警 | 减仓50% ({', '.join(reversal_items)})"

        # 综合建议文字
        if score >= 45:
            signal_emoji = "强势买入"
            suggestion = f"日线EMA5{'金叉' if golden_cross else '在'}EMA10上方，4小时趋势确认，资金流入，技术健康。建议正常仓位做多，等待回踩4h EMA21({fmt_price(ema21_val)})附近入场，止损设在EMA21下方。"
        elif score >= 30:
            signal_emoji = "关注等待"
            if golden_cross or (ema5_val > ema10_val and ema_gap < 0.03):
                suggestion = f"日线底部形态{'确认中' if golden_cross else '接近形成'}，EMA5与EMA10差距很小，4小时趋势确认。等待价格回踩4h EMA21({fmt_price(ema21_val)})附近再入场，不要追涨。"
            else:
                suggestion = f"日线结构{'已确认' if struct_confirm else '向好'}，4小时ADX({adx_val:.1f})处于趋势区。建议关注，等待更好的入场点。"
        elif score >= 15:
            signal_emoji = "轻仓试探"
            suggestion = f"部分指标向好但不够全面，成交量一般。建议小仓位试探，严格止损在4h EMA21({fmt_price(ema21_val)})。"
        elif score <= -30:
            signal_emoji = "强空信号"
            suggestion = f"日线趋势走弱，{'资金费率极端' if abs(funding_rate) >= 0.0005 else '资金偏空'}，技术走弱。建议做空，止损设在前高。"
        elif score <= -15:
            signal_emoji = "关注做空"
            suggestion = f"日线趋势减弱，4小时ADX回落，{'出现顶背离' if '顶背离' in tech_desc else '动能衰竭'}。等待确认后考虑做空。"
        else:
            signal_emoji = "观望"
            if adx_val < CONFIG["ADX_NO_TREND"]:
                suggestion = f"ADX({adx_val:.1f})低于18，多空均无明确方向，属于震荡行情。禁止开单，等待趋势形成。"
            elif adx_val < CONFIG["ADX_TREND"]:
                suggestion = f"ADX({adx_val:.1f})处于过渡区，趋势方向即将选择但尚未明确。建议观望，等待ADX突破25确认方向。"
            else:
                suggestion = "各指标信号不一致，方向不明。建议观望等待更清晰的信号。"

        # 关键价位
        recent_high = close_4h.iloc[-10:].max() if len(close_4h) >= 10 else close_4h.max()
        recent_low = close_4h.iloc[-10:].min() if len(close_4h) >= 10 else close_4h.min()
        if score >= 30: stop_loss = ema21_val * 0.98
        elif score >= 15: stop_loss = recent_low
        elif score <= -15: stop_loss = recent_high
        else: stop_loss = ema21_val

        # 风险
        risks = []
        if abs(funding_rate) >= 0.0008: risks.append(f"资金费率{funding_rate*100:.3f}%极端，{'多头' if funding_rate > 0 else '空头'}拥挤")
        if rsi_val > 75: risks.append(f"RSI严重超买({rsi_val:.0f})，回调风险大")
        elif rsi_val < 25: risks.append(f"RSI严重超卖({rsi_val:.0f})，反弹后可能继续跌")
        dev = abs(c_d - ema10_val) / ema10_val if ema10_val > 0 else 0
        if dev > 0.08: risks.append(f"价格偏离EMA10达{dev*100:.1f}%，偏离过大")
        if vol_ratio < 0.8: risks.append("成交量萎缩，突破可信度低")
        if not risks: risks.append("暂无特别风险")

        result.update({
            'price': price_24h, 'change_1h': change_1h, 'change_4h': change_4h, 'change_24h': change_24h,
            'category': category,
            'daily_struct': daily_struct, 'h4_trend': h4_trend,
            'funding_desc': funding_desc, 'tech_desc': tech_desc,
            'suggestion': suggestion, 'signal_emoji': signal_emoji,
            'reversal_warning': reversal_warning,
            'ema10_d': ema10_val, 'ema21_4h': ema21_val,
            'recent_high': recent_high, 'recent_low': recent_low, 'stop_loss': stop_loss,
            'risks': risks, 'score_internal': score,
        })
        return result


# ============================================================
# Output Formatter
# ============================================================

def fmt_signal(r):
    lines = []
    sym = r['symbol']
    cat_emoji = {"加密货币":"\U0001FA99","美股":"\U0001F4C8","ETF":"\U0001F3E6","大宗商品":"\U0001F6E2"}.get(r['category'], "\U0001FA99")
    price = fmt_price(r['price'])

    lines.append(f"{'\u2501'*56}")
    lines.append(f"{cat_emoji} {sym} | {r['category']} | {price}")
    lines.append(f"    1h: {fmt_pct(r['change_1h'])} | 4h: {fmt_pct(r['change_4h'])} | 24h: {fmt_pct(r['change_24h'])}")
    lines.append(f"{'\u2501'*56}")
    lines.append(f"\n【日线结构】")
    lines.append(f"    {r['daily_struct']}")
    lines.append(f"\n【4小时趋势】")
    lines.append(f"    {r['h4_trend']}")
    lines.append(f"\n【资金状态】")
    lines.append(f"    {r['funding_desc']}")
    lines.append(f"\n【技术状态】")
    lines.append(f"    {r['tech_desc']}")

    emoji_map = {"强势买入":"\U0001F7E2","关注等待":"\U0001F7E1","轻仓试探":"\U0001F7E0","观望":"\U000026AA","强空信号":"\U0001F534","关注做空":"\U0001F7E3"}
    emoji = emoji_map.get(r['signal_emoji'], "\U000026AA")
    lines.append(f"\n【综合建议】")
    lines.append(f"    {emoji} {r['signal_emoji']}：{r['suggestion']}")
    if r['reversal_warning']:
        lines.append(f"\n    \U0001F6A8 !!! {r['reversal_warning']}")

    lines.append(f"\n【关键价位】")
    lines.append(f"    日线EMA10: {fmt_price(r['ema10_d'])} (动态支撑/阻力)")
    lines.append(f"    4h EMA21: {fmt_price(r['ema21_4h'])} (入场/止损参考)")
    lines.append(f"    近10根前高: {fmt_price(r['recent_high'])} | 前低: {fmt_price(r['recent_low'])}")
    lines.append(f"    建议止损: {fmt_price(r['stop_loss'])}")

    lines.append(f"\n【风险提示】")
    for risk in r['risks']:
        lines.append(f"    \u26A0 {risk}")
    lines.append(f"\n{'\u2501'*56}\n")
    return "\n".join(lines)


def fmt_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"\n{'\u2550'*56}\n  \U0001F4CA 币安合约专业分析监控系统 v4.0\n  日线定趋势 / 4H共振 / 15M买卖点\n  {now}\n{'\u2550'*56}"


def fmt_footer(has_signals, total, elapsed):
    lines = [f"\n{'\u2550'*56}"]
    lines.append(f"  \u2705 分析完成 | {'有信号币种: ' + str(total) + '个 | ' if has_signals else ''}耗时: {elapsed:.1f}秒")
    lines.append(f"  \u23F0 下次扫描: 1小时后")
    lines.append(f"{'\u2550'*56}")
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
        signal_results = []
        no_signal_list = []
        error_list = []

        print("正在获取币安活跃永续合约列表...")
        self.valid_symbols = self.collector.fetch_valid_symbols()
        print(f"币安共有 {len(self.valid_symbols)} 个活跃永续合约\n")

        symbols_to_scan = [s for s in WATCHLIST if s in self.valid_symbols]
        skipped = [s for s in WATCHLIST if s not in self.valid_symbols]

        if skipped:
            print(f"以下 {len(skipped)} 个币种不在币安合约列表，已跳过:")
            for s in skipped[:10]: print(f"  \u26A0 {s} 不在币安活跃合约列表")
            if len(skipped) > 10: print(f"  ...等共{len(skipped)}个")
            print()

        print(f"本次扫描: {len(symbols_to_scan)}个币种\n")
        print(fmt_header())
        print(f"\n开始分析 {len(symbols_to_scan)} 个币种...\n")

        for i, sym in enumerate(symbols_to_scan, 1):
            print(f"  [{i:3d}/{len(symbols_to_scan)}] {sym:12s} ...", end=" ", flush=True)

            df_4h = self.collector.get_klines(sym, CONFIG["TF_4H"], CONFIG["LOOKBACK_4H"])
            if df_4h is None or len(df_4h) < 55:
                if self.collector.is_delisted(sym): print("已下架")
                else: print("\u274C 数据异常"); error_list.append(sym)
                continue

            df_1h = self.collector.get_klines(sym, CONFIG["TF_15M"], 100)
            df_daily = self.collector.get_klines(sym, CONFIG["TF_DAILY"], CONFIG["LOOKBACK_DAILY"])
            funding = self.collector.get_funding(sym)
            ticker = self.collector.get_24h_ticker(sym)

            if df_daily is None or len(df_daily) < 15:
                print("日线不足"); error_list.append(sym); continue

            result = self.analyzer.analyze(sym, df_4h, df_1h, df_daily, funding, ticker)

            if result['score_internal'] >= CONFIG["SCORE_MIN"] or result['score_internal'] <= -20 or result['reversal_warning']:
                signal_results.append(result)
                print(f"\u2705 {result['signal_emoji']}")
            else:
                no_signal_list.append(f"{sym}({result['signal_emoji']})")
                print(f"{result['signal_emoji']}")

        elapsed = time.time() - start
        signal_results.sort(key=lambda x: x['score_internal'], reverse=True)

        if signal_results:
            print(f"\n\n{'\u2B50'*28}")
            print(f"  \U0001F4CA 有信号币种详细报告 ({len(signal_results)}个)")
            print(f"{'\u2B50'*28}\n")
            for r in signal_results: print(fmt_signal(r))
        else:
            print(f"\n\n\U0001F4CB 本周期未发现显著交易信号")

        if no_signal_list:
            print(f"\n\U0001F4CB 以下币种无显著信号 ({len(no_signal_list)}个):")
            chunks = [no_signal_list[i:i+8] for i in range(0, len(no_signal_list), 8)]
            for chunk in chunks: print(f"    {' | '.join(chunk)}")

        if error_list:
            print(f"\n\u274C 以下币种数据异常 ({len(error_list)}个):")
            print(f"    {', '.join(error_list[:10])}")
            if len(error_list) > 10: print(f"    ...等共{len(error_list)}个")

        print(fmt_footer(len(signal_results) > 0, len(signal_results), elapsed))
        return signal_results

    def run_continuous(self):
        print(f"\n{'='*56}")
        print("  \U0001F4CA 币安合约专业分析监控系统 v4.0")
        print("  日线定趋势 / 4H共振 / 15M买卖点")
        print("  \u23F0 每1小时自动扫描 | Ctrl+C 停止")
        print(f"{'='*56}\n")
        try:
            while True:
                try: self.run_once()
                except Exception as e: print(f"\n\u274C 扫描出错: {str(e)[:100]}"); print("10分钟后重试..."); time.sleep(600); continue
                now = datetime.now()
                next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait = (next_run - now).total_seconds()
                if wait > 0: print(f"\n\U0001F634 休眠{int(wait/60)}分钟后继续扫描..."); time.sleep(wait)
        except KeyboardInterrupt: print("\n\n\U0001F44B 系统已停止"); sys.exit(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='币安合约专业分析监控系统 v4.0')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    parser.add_argument('--symbol', type=str, help='只分析指定币种')
    args = parser.parse_args(); monitor = BinanceMonitor()

    if args.symbol:
        print(f"单独分析: {args.symbol}")
        monitor.valid_symbols = monitor.collector.fetch_valid_symbols()
        if args.symbol not in monitor.valid_symbols:
            print(f"\u26A0 {args.symbol} 不在币安活跃合约列表"); return
        df_4h = monitor.collector.get_klines(args.symbol, CONFIG["TF_4H"], CONFIG["LOOKBACK_4H"])
        df_1h = monitor.collector.get_klines(args.symbol, CONFIG["TF_15M"], 100)
        df_daily = monitor.collector.get_klines(args.symbol, CONFIG["TF_DAILY"], CONFIG["LOOKBACK_DAILY"])
        funding = monitor.collector.get_funding(args.symbol)
        ticker = monitor.collector.get_24h_ticker(args.symbol)
        if df_4h is not None and df_daily is not None:
            r = monitor.analyzer.analyze(args.symbol, df_4h, df_1h, df_daily, funding, ticker)
            print(fmt_signal(r))
        else: print("\u274C 数据获取失败")
    elif args.once: monitor.run_once()
    else: monitor.run_continuous()


if __name__ == "__main__":
    main()
