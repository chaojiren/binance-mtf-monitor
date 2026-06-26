#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安合约MTF多时间框架共振监控系统
日线定趋势 -> 4小时共振 -> 15分钟找买卖点
版本: 2.0.0
"""

import requests
import pandas as pd
import numpy as np
import time
import sys
from datetime import datetime, timedelta

# ============================================================
# 1. 可配置参数
# ============================================================

WATCHLIST = [
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
    "EWJUSDT","EWZUSDT","XLEUSDT","URNMUSDT","UVXYUSDT","KORUUSDT","MVLLUSDT","TQQQUSDT","SQQQUSDT","XAUUSDT",
    "XAGUSDT","XPTUSDT","XPDUSDT","COPPERUSDT","CLUSDT","NATGASUSDT"
]

TF_DAILY, TF_4H, TF_15M = "1d", "4h", "15m"
LOOKBACK_DAILY, LOOKBACK_4H, LOOKBACK_15M = 90, 100, 100
REQUEST_DELAY, MAX_RETRIES = 0.3, 3
CONSECUTIVE_FAIL_THRESHOLD = 3
BASE_URL = "https://fapi.binance.com"
KLINES_ENDPOINT = "/fapi/v1/klines"

CATEGORY_MAP = {"BTCUSDT":"CRYPTO","ETHUSDT":"CRYPTO","SOLUSDT":"CRYPTO","BNBUSDT":"CRYPTO","XRPUSDT":"CRYPTO","DOGEUSDT":"CRYPTO","ADAUSDT":"CRYPTO","AVAXUSDT":"CRYPTO","TRXUSDT":"CRYPTO","DOTUSDT":"CRYPTO","AAPLUSDT":"STOCK","MSFTUSDT":"STOCK","GOOGLUSDT":"STOCK","AMZNUSDT":"STOCK","METAUSDT":"STOCK","NVDAUSDT":"STOCK","TSLAUSDT":"STOCK","NFLXUSDT":"STOCK","AMDUSDT":"STOCK","INTCUSDT":"STOCK","ORCLUSDT":"STOCK","CSCOUSDT":"STOCK","IBMUSDT":"STOCK","CRMUSDT":"STOCK","NOWUSDT":"STOCK","DELLUSDT":"STOCK","HPEUSDT":"STOCK","SAMSUNGUSDT":"STOCK","SONYUSDT":"STOCK","TSMUSDT":"STOCK","AVGOUSDT":"STOCK","QCOMUSDT":"STOCK","MUUSDT":"STOCK","ARMUSDT":"STOCK","WDCUSDT":"STOCK","SNDKUSDT":"STOCK","LITEUSDT":"STOCK","ASMLUSDT":"STOCK","LRCXUSDT":"STOCK","KLACUSDT":"STOCK","AMATUSDT":"STOCK","SMCIUSDT":"STOCK","CIENUSDT":"STOCK","COHRUSDT":"STOCK","CRDOUSDT":"STOCK","MRVLUSDT":"STOCK","STXXUSDT":"STOCK","GLWUSDT":"STOCK","ASTSUSDT":"STOCK","SKHYNIXUSDT":"STOCK","CRWDUSDT":"STOCK","VUSDT":"STOCK","JPMUSDT":"STOCK","BRKBUSDT":"STOCK","BXUSDT":"STOCK","HOODUSDT":"STOCK","COINUSDT":"STOCK","PAYPUSDT":"STOCK","CRCLUSDT":"STOCK","AAOIUSDT":"STOCK","MSTRUSDT":"STOCK","BABAUSDT":"STOCK","WMTUSDT":"STOCK","HDUSDT":"STOCK","COSTUSDT":"STOCK","DISUSDT":"STOCK","UBERUSDT":"STOCK","EBAYUSDT":"STOCK","DKNGUSDT":"STOCK","GMEUSDT":"STOCK","BBXUSDT":"STOCK","NOKUSDT":"STOCK","HYUNDAIUSDT":"STOCK","LLYUSDT":"STOCK","NVOUSDT":"STOCK","HIMSUSDT":"STOCK","USARUSDT":"STOCK","FLNCUSDT":"STOCK","BEUSDT":"STOCK","ONDSUSDT":"STOCK","BMNRUSDT":"STOCK","PLTRUSDT":"STOCK","RKLBUSDT":"STOCK","SPCXUSDT":"STOCK","OPENAIUSDT":"STOCK_RISK","ANTHROPICUSDT":"STOCK_RISK","NBISUSDT":"STOCK","CBRSUSDT":"STOCK","CRWVUSDT":"STOCK","QNTXUSDT":"STOCK","IRENUSDT":"STOCK","DRAMUSDT":"STOCK","SPYUSDT":"ETF","QQQUSDT":"ETF","IWMUSDT":"ETF","SOXLUSDT":"ETF","EWTUSDT":"ETF","EWYUSDT":"ETF","EWJUSDT":"ETF","EWZUSDT":"ETF","XLEUSDT":"ETF","URNMUSDT":"ETF","UVXYUSDT":"ETF","KORUUSDT":"ETF","MVLLUSDT":"ETF","TQQQUSDT":"ETF","SQQQUSDT":"ETF","XAUUSDT":"COMMODITY","XAGUSDT":"COMMODITY","XPTUSDT":"COMMODITY","XPDUSDT":"COMMODITY","COPPERUSDT":"COMMODITY","CLUSDT":"COMMODITY","NATGASUSDT":"COMMODITY"}
PRE_MARKET_RISK = ["OPENAIUSDT","ANTHROPICUSDT"]


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calc_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_f = calc_ema(close, fast)
    ema_s = calc_ema(close, slow)
    macd_line = ema_f - ema_s
    sig_line = calc_ema(macd_line, signal)
    return macd_line, sig_line, macd_line - sig_line


def calc_bb(close, period=20, mult=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + std*mult, mid, mid - std*mult


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
    return f"{s}{v:.2f}%"


class DataCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        self.failures = {}

    def get_klines(self, symbol, interval, limit):
        url = f"{BASE_URL}{KLINES_ENDPOINT}"
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(REQUEST_DELAY)
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code == 429:
                    time.sleep(2 ** attempt); continue
                if resp.status_code != 200:
                    if attempt < MAX_RETRIES: time.sleep(1); continue
                    return None
                data = resp.json()
                if not isinstance(data, list) or len(data) == 0: return None
                return self._parse(data)
            except Exception:
                if attempt < MAX_RETRIES: time.sleep(1); continue
                return None
        return None

    def get_all_tfs(self, symbol):
        df_d = self.get_klines(symbol, TF_DAILY, LOOKBACK_DAILY)
        if df_d is None or len(df_d) < 55: return None, None, None
        df_4h = self.get_klines(symbol, TF_4H, LOOKBACK_4H)
        if df_4h is None or len(df_4h) < 55: return None, None, None
        df_15m = self.get_klines(symbol, TF_15M, LOOKBACK_15M)
        if df_15m is None or len(df_15m) < 55: return None, None, None
        return df_d, df_4h, df_15m

    def _parse(self, data):
        cols = ['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy','taker_buy_quote','ignore']
        df = pd.DataFrame(data, columns=cols)
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        return df

    def is_delisted(self, symbol):
        if symbol not in self.failures: self.failures[symbol] = 0
        self.failures[symbol] += 1
        return self.failures[symbol] >= CONSECUTIVE_FAIL_THRESHOLD


class MTFAnalyzer:
    def analyze(self, symbol, df_d, df_4h, df_15m):
        daily_trend = self._daily_trend(df_d)
        if daily_trend['trend'] == 'UNKNOWN': return None
        h4_align = self._h4_alignment(df_4h, daily_trend['trend'])
        m15_signal = self._m15_entry(df_15m, daily_trend['trend'])
        aligned = (daily_trend['trend'] == h4_align['direction'])
        if m15_signal['signal_type'] == 'NONE': return None
        resonance_score = self._calc_resonance(daily_trend, h4_align, m15_signal)
        if resonance_score < 30: return None
        return {
            'symbol': symbol, 'category': CATEGORY_MAP.get(symbol, "STOCK"),
            'daily_trend': daily_trend['trend'], 'daily_trend_emoji': self._trend_emoji(daily_trend['trend']),
            'daily_adx': daily_trend['adx'], 'daily_price': daily_trend['price'],
            'h4_direction': h4_align['direction'], 'h4_adx': h4_align['adx'], 'h4_aligned': aligned,
            'm15_signal': m15_signal['signal_type'], 'm15_entry_price': m15_signal['entry_price'],
            'm15_stop_loss': m15_signal['stop_loss'], 'm15_take_profit': m15_signal['take_profit'],
            'm15_rsi': m15_signal['rsi'], 'm15_risk_reward': m15_signal['risk_reward'],
            'm15_bb_position': m15_signal['bb_position'], 'm15_reason': m15_signal.get('reason', []),
            'resonance_score': resonance_score, 'confidence': self._score_to_confidence(resonance_score, aligned),
            'suggestion': self._suggestion(daily_trend['trend'], m15_signal['signal_type'], aligned),
            'is_pre_market': symbol in PRE_MARKET_RISK,
            'is_commodity': "COMMODITY" in CATEGORY_MAP.get(symbol, ""),
            'is_etf': "ETF" in CATEGORY_MAP.get(symbol, "")
        }

    def _daily_trend(self, df):
        close, high, low = df['close'], df['high'], df['low']
        ema20, ema50, ema200 = calc_ema(close, 20), calc_ema(close, 50), calc_ema(close, 200)
        adx, _, _ = calc_adx(high, low, close, 14)
        c, e20, e50, e200 = close.iloc[-1], ema20.iloc[-1], ema50.iloc[-1], ema200.iloc[-1]
        adx_val = adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0
        bull_aligned = (e20 > e50 > e200) and (c > e20)
        bear_aligned = (e20 < e50 < e200) and (c < e20)
        strong_trend = adx_val >= 25
        if bull_aligned: trend = 'BULL' if strong_trend else 'BULL_WEAK'
        elif bear_aligned: trend = 'BEAR' if strong_trend else 'BEAR_WEAK'
        else:
            if c > e50 and adx_val < 20: trend = 'BULL_RANGE'
            elif c < e50 and adx_val < 20: trend = 'BEAR_RANGE'
            else: trend = 'RANGE'
        return {'trend': trend, 'price': c, 'ema20': e20, 'ema50': e50, 'ema200': e200, 'adx': adx_val, 'price_vs_ema50': (c - e50) / e50 * 100}

    def _h4_alignment(self, df, daily_trend):
        close, high, low = df['close'], df['high'], df['low']
        ema20, ema50 = calc_ema(close, 20), calc_ema(close, 50)
        adx, pdi, ndi = calc_adx(high, low, close, 14)
        macd_line, sig_line, hist = calc_macd(close, 12, 26, 9)
        c, e20, e50 = close.iloc[-1], ema20.iloc[-1], ema50.iloc[-1]
        adx_val = adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0
        if c > e20 > e50: direction = 'BULL'
        elif c < e20 < e50: direction = 'BEAR'
        elif c > e50: direction = 'BULL_RANGE'
        elif c < e50: direction = 'BEAR_RANGE'
        else: direction = 'RANGE'
        macd_bull = macd_line.iloc[-1] > sig_line.iloc[-1]
        return {'direction': direction, 'adx': adx_val, 'macd_bull': macd_bull, 'price_vs_ema20': (c - e20) / e20 * 100}

    def _m15_entry(self, df, daily_trend):
        close, high, low, volume = df['close'], df['high'], df['low'], df['volume']
        rsi = calc_rsi(close, 14)
        macd_line, sig_line, hist = calc_macd(close, 12, 26, 9)
        bb_up, bb_mid, bb_low = calc_bb(close, 20, 2)
        vol_ma = calc_vol_ma(volume, 20)
        c, h, l = close.iloc[-1], high.iloc[-1], low.iloc[-1]
        rsi_val = rsi.iloc[-1]
        rsi_prev = rsi.iloc[-5] if len(rsi) >= 5 else rsi.iloc[-1]
        macd_curr, macd_sig = macd_line.iloc[-1], sig_line.iloc[-1]
        macd_prev, macd_sig_prev = macd_line.iloc[-2], sig_line.iloc[-2]
        vol_ratio = volume.iloc[-1] / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 0
        bb_range = bb_up.iloc[-1] - bb_low.iloc[-1]
        bb_pos = 50 if bb_range == 0 else (c - bb_low.iloc[-1]) / bb_range * 100
        result = {'signal_type': 'NONE', 'entry_price': c, 'stop_loss': None, 'take_profit': None, 'rsi': rsi_val, 'risk_reward': 0, 'bb_position': bb_pos, 'reason': []}
        is_bull = daily_trend in ['BULL', 'BULL_WEAK', 'BULL_RANGE']
        is_bear = daily_trend in ['BEAR', 'BEAR_WEAK', 'BEAR_RANGE']
        if is_bull:
            reasons = []
            if rsi_val > 35 and rsi_prev <= 40: reasons.append("RSI超卖回升")
            if macd_curr > macd_sig and macd_prev <= macd_sig_prev: reasons.append("MACD金叉")
            if bb_pos <= 15 and c > l: reasons.append("布林带下轨反弹")
            if 30 <= rsi_val <= 45 and bb_pos <= 25: reasons.append("低位RSI+下轨")
            if vol_ratio >= 1.5 and c > df['open'].iloc[-1]: reasons.append("放量阳线")
            if len(reasons) >= 1:
                result['signal_type'] = 'BUY'; result['reason'] = reasons
                result['stop_loss'] = min(l, bb_low.iloc[-1] * 0.998)
                result['take_profit'] = bb_up.iloc[-1] * 1.002
                result['risk_reward'] = (result['take_profit'] - c) / (c - result['stop_loss']) if (c - result['stop_loss']) > 0 else 0
        elif is_bear:
            reasons = []
            if rsi_val < 65 and rsi_prev >= 60: reasons.append("RSI超买回落")
            if macd_curr < macd_sig and macd_prev >= macd_sig_prev: reasons.append("MACD死叉")
            if bb_pos >= 85 and c < h: reasons.append("布林带上轨回落")
            if 55 <= rsi_val <= 70 and bb_pos >= 75: reasons.append("高位RSI+上轨")
            if vol_ratio >= 1.5 and c < df['open'].iloc[-1]: reasons.append("放量阴线")
            if len(reasons) >= 1:
                result['signal_type'] = 'SELL'; result['reason'] = reasons
                result['stop_loss'] = max(h, bb_up.iloc[-1] * 1.002)
                result['take_profit'] = bb_low.iloc[-1] * 0.998
                result['risk_reward'] = (result['stop_loss'] - c) / (c - result['take_profit']) if (c - result['take_profit']) > 0 else 0
        return result

    def _calc_resonance(self, daily, h4, m15):
        score, daily_trend = 0, daily['trend']
        if 'BULL' in daily_trend or 'BEAR' in daily_trend: score += 40 if daily['adx'] >= 25 else 25
        elif 'RANGE' in daily_trend: score += 10
        aligned = daily_trend.replace('_WEAK','').replace('_RANGE','') == h4['direction'].replace('_WEAK','').replace('_RANGE','')
        if aligned: score += 30
        elif h4['direction'] != 'RANGE': score += 10
        if m15['signal_type'] != 'NONE':
            signal_count = len(m15.get('reason', []))
            score += min(signal_count * 10, 30)
            if m15['risk_reward'] >= 2: score += 5
            if m15['risk_reward'] >= 3: score += 5
        return min(score, 100)

    def _trend_emoji(self, trend):
        return {'BULL': '强多头', 'BULL_WEAK': '弱多头', 'BULL_RANGE': '震荡偏多', 'BEAR': '强空头', 'BEAR_WEAK': '弱空头', 'BEAR_RANGE': '震荡偏空', 'RANGE': '震荡'}.get(trend, '未知')

    def _score_to_confidence(self, score, aligned):
        if not aligned: return "低(4h未共振)"
        if score >= 80: return "高"
        if score >= 60: return "中高"
        if score >= 45: return "中"
        return "低"

    def _suggestion(self, trend, signal, aligned):
        if not aligned: return "4h未共振,建议观望等待"
        if signal == 'BUY': return "顺势做多,严格止损" if 'BULL' in trend else "逆势反弹,极小仓位"
        elif signal == 'SELL': return "顺势做空,严格止损" if 'BEAR' in trend else "逆势回调,极小仓位"
        return "观望"


class OutputFormatter:
    @staticmethod
    def format_mtf_signal(r):
        lines = []
        sym, cat, price, trend, sig = r['symbol'], r['category'], fmt_price(r['m15_entry_price']), r['daily_trend_emoji'], r['m15_signal']
        sig_emoji = '做多' if sig == 'BUY' else '做空'
        lines.append(f"{'='*52}")
        lines.append(f"[{sig_emoji}] [{cat}] {sym} | {price}")
        lines.append(f"{'='*52}")
        lines.append(f"日线趋势: {trend} (ADX:{r['daily_adx']:.1f})")
        h4_status = "共振" if r['h4_aligned'] else "未共振"
        h4_emoji = "多头" if "BULL" in r['h4_direction'] else "空头" if "BEAR" in r['h4_direction'] else "震荡"
        lines.append(f"4H共振:   {h4_emoji} {r['h4_direction']} {h4_status} (ADX:{r['h4_adx']:.1f})")
        m15_reasons = r.get('m15_reason', [])
        reasons = " + ".join(m15_reasons) if isinstance(m15_reasons, list) and m15_reasons else "技术指标触发"
        lines.append(f"15M信号:  {reasons}")
        rr, bb_pos, rsi = r['m15_risk_reward'], r['m15_bb_position'], r['m15_rsi']
        bb_desc = "下轨" if bb_pos <= 20 else "中轨" if bb_pos <= 80 else "上轨"
        lines.append(f"RSI:{rsi:.1f} | 布林带:{bb_desc}({bb_pos:.0f}%) | 盈亏比:{rr:.1f}:1")
        if r['m15_stop_loss'] and r['m15_take_profit']:
            sl, tp = fmt_price(r['m15_stop_loss']), fmt_price(r['m15_take_profit'])
            lines.append(f"入场: {price} | 止损: {sl} | 止盈: {tp}")
        conf, score = r['confidence'], r['resonance_score']
        score_bar = "#" * int(score/10) + "-" * (10 - int(score/10))
        lines.append(f"共振评分: [{score_bar}] {score}/100 | 置信度: {conf}")
        lines.append(f"建议: {r['suggestion']}")
        if r['is_pre_market']: lines.append("注意: 该币种处于美股盘前/盘后阶段,流动性极低")
        if r['is_commodity']: lines.append("注意: 大宗商品,关注期货市场开盘时间")
        if r['is_etf']: lines.append("注意: ETF资产,关注美股大盘走势")
        lines.append(""); return "\n".join(lines)

    @staticmethod
    def format_header():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = ["=" * 52, "币安MTF共振监控系统", "日线趋势 -> 4H共振 -> 15M买卖点", f"监控{len(WATCHLIST)}个币种 | {now}", "=" * 52]
        return "\n".join(lines)

    @staticmethod
    def format_no_signals(scanned, bull_count, bear_count, range_count):
        lines = ["\n本周期无共振交易信号", f"扫描{scanned}个币种 | 多头趋势{bull_count}个 | 空头趋势{bear_count}个 | 震荡{range_count}个", "下次扫描: 1小时后"]
        return "\n".join(lines)

    @staticmethod
    def format_footer(signal_count, elapsed):
        lines = ["=" * 52, f"完成 | 共振信号: {signal_count}个 | 耗时: {elapsed:.1f}秒", f"下次: {(datetime.now() + timedelta(hours=1)).strftime('%H:%M:%S')}", "=" * 52]
        return "\n".join(lines)


class BinanceMTFMonitor:
    def __init__(self):
        self.collector = DataCollector()
        self.analyzer = MTFAnalyzer()
        self.formatter = OutputFormatter()

    def run_once(self):
        start, signals, scanned = time.time(), [], 0
        bull_count = bear_count = range_count = 0
        delisted = []
        print("\n" + self.formatter.format_header())
        print(f"\n开始MTF三级分析 {len(WATCHLIST)} 个币种...")
        print(f"日线趋势({TF_DAILY}) -> 4H共振({TF_4H}) -> 15M买卖点({TF_15M})\n")
        for i, sym in enumerate(WATCHLIST, 1):
            print(f"  [{i:3d}/{len(WATCHLIST)}] {sym:12s} ...", end=" ", flush=True)
            df_d, df_4h, df_15m = self.collector.get_all_tfs(sym)
            if df_d is None:
                if self.collector.is_delisted(sym): print("已下架"); delisted.append(sym)
                else: print("数据失败")
                continue
            scanned += 1; result = self.analyzer.analyze(sym, df_d, df_4h, df_15m)
            if result:
                if 'BULL' in result['daily_trend']: bull_count += 1
                elif 'BEAR' in result['daily_trend']: bear_count += 1
                else: range_count += 1
                signals.append(result); sig_type = "多" if result['m15_signal'] == 'BUY' else "空"
                print(f"OK {sig_type} 评分{result['resonance_score']}")
            else:
                daily_t = self.analyzer._daily_trend(df_d)['trend']
                if 'BULL' in daily_t: bull_count += 1
                elif 'BEAR' in daily_t: bear_count += 1
                else: range_count += 1
                print("无信号")
        elapsed = time.time() - start
        if signals:
            signals.sort(key=lambda x: x['resonance_score'], reverse=True)
            print(f"\n{'='*52}"); print(f"发现 {len(signals)} 个共振交易信号"); print(f"多头趋势{bull_count}个 | 空头趋势{bear_count}个 | 震荡{range_count}个"); print(f"{'='*52}\n")
            for r in signals: print(self.formatter.format_mtf_signal(r))
        else: print(self.formatter.format_no_signals(scanned, bull_count, bear_count, range_count))
        if delisted: print(f"\n可能已下架({len(delisted)}个): {', '.join(delisted[:10])}")
        print(self.formatter.format_footer(len(signals), elapsed)); return signals

    def run_continuous(self):
        print("\n" + "=" * 52); print("币安MTF共振监控系统启动"); print("日线定趋势 -> 4H共振 -> 15M买卖点"); print("每1小时自动扫描 | Ctrl+C 停止"); print("=" * 52 + "\n")
        try:
            while True:
                try: self.run_once()
                except Exception as e: print(f"\n扫描出错: {str(e)[:100]}"); print("10分钟后重试..."); time.sleep(600); continue
                now = datetime.now(); next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1); wait = (next_run - now).total_seconds()
                if wait > 0: print(f"\n休眠{int(wait/60)}分钟..."); time.sleep(wait)
        except KeyboardInterrupt: print("\n\n已停止"); sys.exit(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='币安MTF共振监控系统')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    parser.add_argument('--symbol', type=str, help='只分析指定币种')
    args = parser.parse_args(); monitor = BinanceMTFMonitor()
    if args.symbol:
        print(f"单独分析: {args.symbol}"); df_d, df_4h, df_15m = monitor.collector.get_all_tfs(args.symbol)
        if df_d is not None:
            r = monitor.analyzer.analyze(args.symbol, df_d, df_4h, df_15m)
            if r: print(monitor.formatter.format_mtf_signal(r))
            else: trend = monitor.analyzer._daily_trend(df_d); print(f"日线趋势: {trend['trend']}"); print("15M暂无明确买卖点信号")
        else: print("数据获取失败")
    elif args.once: monitor.run_once()
    else: monitor.run_continuous()

if __name__ == "__main__":
    main()
