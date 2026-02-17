import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class Point:
    index: int
    price: float
    time: int  # Timestamp

@dataclass
class Pattern:
    name: str
    direction: str  # "Bullish" or "Bearish"
    points: List[Point]  # Key points for visualization
    error: float = 0.0

class ChartPatternAnalyzer:
    def __init__(self, err_allowed=0.15):
        self.err_allowed = err_allowed

    def is_hammer(self, open_p, high_p, low_p, close_p) -> bool:
        body = abs(close_p - open_p)
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        # 下影线至少是实体的2倍，且几乎没有上影线
        return lower_wick >= 2 * body and upper_wick <= 0.1 * lower_wick and body > 0

    def is_shooting_star(self, open_p, high_p, low_p, close_p) -> bool:
        body = abs(close_p - open_p)
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        # 上影线至少是实体的2倍，且几乎没有下影线
        return upper_wick >= 2 * body and lower_wick <= 0.1 * upper_wick and body > 0

    def analyze(self, klines_data: List[List[Any]], tolerance: float = None) -> List[Pattern]:
        if not klines_data:
            return []
            
        df = pd.DataFrame(klines_data, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'close_time', 'qav', 'num_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        
        results = []
        # 只分析最近的 150 根 K 线，避免太多标注
        lookback = 150
        start_idx = max(1, len(df) - lookback)

        for i in range(start_idx, len(df)):
            o, h, l, c = df.iloc[i][['open', 'high', 'low', 'close']]
            prev_o, prev_c = df.iloc[i-1][['open', 'close']]
            time_val = int(df.iloc[i]['time'])
            
            # --- 1. 锤子线 (Hammer) ---
            if self.is_hammer(o, h, l, c):
                # 简单趋势判断：当前价格低于前一根或处于近期低位
                results.append(Pattern(
                    name="Hammer (锤子线)",
                    direction="Bullish",
                    points=[Point(i, l, time_val)]
                ))

            # --- 2. 倒锤子线 (Inverted Hammer) ---
            elif self.is_shooting_star(o, h, l, c) and c < o:
                # 在底部出现的倒锤子
                results.append(Pattern(
                    name="Inv Hammer (倒锤子)",
                    direction="Bullish",
                    points=[Point(i, h, time_val)]
                ))

            # --- 3. 流星线 (Shooting Star) ---
            elif self.is_shooting_star(o, h, l, c) and c > o * 1.001:
                results.append(Pattern(
                    name="Shooting Star (流星)",
                    direction="Bearish",
                    points=[Point(i, h, time_val)]
                ))

            # --- 4. 吞没形态 (Engulfing) ---
            curr_body_max = max(o, c)
            curr_body_min = min(o, c)
            prev_body_max = max(prev_o, prev_c)
            prev_body_min = min(prev_o, prev_c)

            if curr_body_max > prev_body_max and curr_body_min < prev_body_min:
                if c > o: # Bullish Engulfing
                    results.append(Pattern(
                        name="Bullish Engulfing (看涨吞没)",
                        direction="Bullish",
                        points=[Point(i, l, time_val)]
                    ))
                else: # Bearish Engulfing
                    results.append(Pattern(
                        name="Bearish Engulfing (看跌吞没)",
                        direction="Bearish",
                        points=[Point(i, h, time_val)]
                    ))

            # --- 5. 十字星 (Doji) ---
            body = abs(c - o)
            total_range = h - l
            if total_range > 0 and body / total_range < 0.1:
                 results.append(Pattern(
                    name="Doji (十字星)",
                    direction="Neutral",
                    points=[Point(i, c, time_val)]
                ))

        # 排序并去重
        results.sort(key=lambda x: x.points[0].index, reverse=True)
        return results[:10] # 每次只显示最重要的 10 个信号

pattern_recognizer = ChartPatternAnalyzer()
