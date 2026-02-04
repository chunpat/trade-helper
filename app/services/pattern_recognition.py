import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
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
    points: List[Point]  # [X, A, B, C, D]
    error: float  # Error margin average

class HarmonicPatternRead:
    def __init__(self, err_allowed=0.20):
        self.err_allowed = err_allowed

    def find_peaks_troughs(self, df: pd.DataFrame, order=5) -> List[Point]:
        """
        Simple peak/trough detection
        df should have 'high', 'low', 'close', 'open', 'time' columns
        """
        # Using simple local extrema
        points = []
        
        # Convert to numpy for speed
        highs = df['high'].values
        lows = df['low'].values
        times = df['time'].values
        
        # Naive zigzag implementation or finding local extrema with a window
        # We search for local maximums and minimums within 'order' lookback/lookforward
        
        for i in range(order, len(df) - order):
            # Check for High
            if all(highs[i] >= highs[i-j] for j in range(1, order+1)) and \
               all(highs[i] >= highs[i+j] for j in range(1, order+1)):
                points.append(Point(i, highs[i], times[i]))
            
            # Check for Low
            if all(lows[i] <= lows[i-j] for j in range(1, order+1)) and \
               all(lows[i] <= lows[i+j] for j in range(1, order+1)):
                # If we have a high at the same index (unlikely but possible in this naive loop), 
                # we technically mark both. But usually we want alternating.
                # For simplicity, we just add it.
                points.append(Point(i, lows[i], times[i]))

        # Filter strictly alternating High/Low for zigzag
        # This is a simplified approach. A proper ZigZag usually uses % dev or ATR.
        
        if not points:
            return []

        clean_points = [points[0]]
        for p in points[1:]:
            last_p = clean_points[-1]
            
            # Identify if current p is a High or Low relative to neighbors logic
            # But here we just have a list of extremas.
            # We need to know if it's top or bottom. 
            # In the loop above, we can tag them.
            pass
        
        # Let's re-run loop and tag type
        tagged_points = []
        for i in range(order, len(df) - order):
            is_high = all(highs[i] >= highs[i-j] for j in range(1, order+1)) and \
                      all(highs[i] >= highs[i+j] for j in range(1, order+1))
            
            is_low = all(lows[i] <= lows[i-j] for j in range(1, order+1)) and \
                     all(lows[i] <= lows[i+j] for j in range(1, order+1))
            
            if is_high:
                tagged_points.append({'type': 'high', 'p': Point(i, highs[i], times[i])})
            elif is_low:
                tagged_points.append({'type': 'low', 'p': Point(i, lows[i], times[i])})

        # Now filter for alternating
        final_points = []
        if not tagged_points:
            return []

        curr = tagged_points[0]
        final_points.append(curr['p'])
        
        for next_p in tagged_points[1:]:
            if next_p['type'] != curr['type']:
                final_points.append(next_p['p'])
                curr = next_p
            else:
                # If same type, take the more extreme one
                if curr['type'] == 'high':
                    if next_p['p'].price > curr['p'].price:
                        final_points.pop()
                        final_points.append(next_p['p'])
                        curr = next_p
                else: # low
                    if next_p['p'].price < curr['p'].price:
                        final_points.pop()
                        final_points.append(next_p['p'])
                        curr = next_p
                        
        return final_points

    def check_ratios(self, val, target, err):
        return abs(val - target) <= err * target

    def find_patterns(self, points: List[Point], tolerance: float = None) -> List[Pattern]:
        patterns = []
        err = tolerance if tolerance is not None else self.err_allowed
        
        # Check for confirmed 5-point patterns
        if len(points) >= 5:
            for i in range(len(points) - 4):
                pts = points[i : i+5]
                X, A, B, C, D = pts
                
                # Check zigzag validity
                # A B C D should alternate highs and lows is guaranteed by find_peaks_troughs if implemented correctly
                # But let's check direction logic
                
                direction = ""
                # Bullish: X(Low) -> A(High) -> B(Low) -> C(High) -> D(Low)
                if X.price < A.price and B.price < A.price and C.price > B.price and D.price < C.price:
                    direction = "Bullish"
                # Bearish: X(High) -> A(Low) -> B(High) -> C(Low) -> D(High)
                elif X.price > A.price and B.price > A.price and C.price < B.price and D.price > C.price:
                    direction = "Bearish"
                else:
                    continue

                # Calculate Heights
                hXA = abs(X.price - A.price)
                hAB = abs(A.price - B.price)
                hBC = abs(B.price - C.price)
                hCD = abs(C.price - D.price)
                
                if hXA == 0 or hAB == 0 or hBC == 0:
                    continue

                # Ratios
                r_xb = hAB / hXA
                r_ac = hBC / hAB
                r_bd = hCD / hBC
                r_ad_xa = abs(D.price - A.price) / hXA

                # --- Gartley ---
                if self.check_ratios(r_xb, 0.618, err) and \
                self.check_ratios(r_ad_xa, 0.786, err) and \
                (0.382 <= r_ac <= 0.886) and \
                (1.1 <= r_bd <= 1.8): # Relaxed BD
                    patterns.append(Pattern("Gartley", direction, pts, 0))

                # --- Bat ---
                if (0.382*(1-err) <= r_xb <= 0.5*(1+err)) and \
                self.check_ratios(r_ad_xa, 0.886, err) and \
                (1.618*(1-err) <= r_bd <= 2.618*(1+err)):
                    patterns.append(Pattern("Bat", direction, pts, 0))

                # --- Butterfly ---
                if self.check_ratios(r_xb, 0.786, err) and \
                (1.27*(1-err) <= r_ad_xa <= 1.618*(1+err)) and \
                (1.618*(1-err) <= r_bd <= 2.618*(1+err)):
                    patterns.append(Pattern("Butterfly", direction, pts, 0))

                # --- Crab ---
                if (0.382*(1-err) <= r_xb <= 0.618*(1+err)) and \
                self.check_ratios(r_ad_xa, 1.618, err) and \
                (2.24*(1-err) <= r_bd <= 3.618*(1+err)):
                    patterns.append(Pattern("Crab", direction, pts, 0))

                # --- Cypher ---
                # XB: 0.382 - 0.618
                # AC: 1.13 - 1.414 (Extension, C goes beyond A)
                # XD: 0.786
                if (0.382*(1-err) <= r_xb <= 0.618*(1+err)) and \
                (1.13*(1-err) <= r_ac <= 1.414*(1+err)) and \
                self.check_ratios(r_ad_xa, 0.786, err):
                     patterns.append(Pattern("Cypher", direction, pts, 0))

                # --- Shark ---
                # XA, AB, BC, CD (Standard 5 points labeling)
                # Note: Traditional Shark starts 0, X, A, B, C. 
                # Our X=0, A=X, B=A, C=B, D=C.
                # Key Ratios (Mapped to XABCD):
                # AB/XA (r_xb): 1.13 - 1.618 (B breaks X)
                # BC/AB (r_ac): 1.618 - 2.24 (C extends AB)
                # XD/XC (r_xd_xc): 0.886 - 1.13 (Target)
                # For simplicity, we check r_xb and r_ac primarily
                if (1.13*(1-err) <= r_xb <= 1.618*(1+err)) and \
                (1.618*(1-err) <= r_ac <= 2.24*(1+err)) and \
                (0.886*(1-err) <= r_ad_xa <= 1.13*(1+err)): # Approx check for final leg
                     patterns.append(Pattern("Shark", direction, pts, 0))

        # Check for POTENTIAL 4-point patterns (forming D)
        # Use the LAST 4 points available to see if a pattern is forming at the current price action
        if len(points) >= 4:
            # We only look at the VERY LAST 4 points to predict the NEXT move
            pts = points[-4:]
            X, A, B, C = pts
            
            # Identify potential direction
            direction = ""
            is_valid_structure = False
            
            # Potential Bullish: X(Low)->A(High)->B(Low)->C(High) -> Waiting for D(Low)
            if X.price < A.price and B.price < A.price and C.price > B.price:
                 direction = "Bullish"
                 is_valid_structure = True
            # Potential Bearish: X(High)->A(Low)->B(High)->C(Low) -> Waiting for D(High)
            elif X.price > A.price and B.price > A.price and C.price < B.price:
                 direction = "Bearish"
                 is_valid_structure = True
            
            if is_valid_structure:
                hXA = abs(X.price - A.price)
                hAB = abs(A.price - B.price)
                hBC = abs(B.price - C.price)
                
                if hXA > 0 and hAB > 0:
                    r_xb = hAB / hXA
                    r_ac = hBC / hAB
                    
                    # Store potential patterns with predicted D
                    
                    # Gartley Formation Check (XB ~ 0.618)
                    if self.check_ratios(r_xb, 0.618, err) and (0.382 <= r_ac <= 0.886):
                        # Predict D at 0.786 Retracement of XA
                        # Bullish (D connects from C down to D): D < C. D = A - 0.786*XA
                        # Bearish (D connects from C up to D): D > C. D = A + 0.786*XA
                        d_dist = 0.786 * hXA
                        d_price = A.price - d_dist if direction == "Bullish" else A.price + d_dist
                        
                        # Create a virtual Point for D (Time is unknown, just future)
                        # We use C.time + (C.time - B.time) roughly for visualization or just mark price
                        predicted_D = Point(0, d_price, 0) 
                        patterns.append(Pattern("Gartley (Potential)", direction, [X, A, B, C, predicted_D], 0))

                    # Bat Formation Check (XB <= 0.5)
                    elif (0.382*(1-err) <= r_xb <= 0.5*(1+err)) and (0.382 <= r_ac <= 0.886):
                        d_dist = 0.886 * hXA
                        d_price = A.price - d_dist if direction == "Bullish" else A.price + d_dist
                        predicted_D = Point(0, d_price, 0)
                        patterns.append(Pattern("Bat (Potential)", direction, [X, A, B, C, predicted_D], 0))

                    # Butterfly Formation Check (XB ~ 0.786)
                    elif self.check_ratios(r_xb, 0.786, err) and (0.382 <= r_ac <= 0.886):
                        # D is external at 1.27 extension of XA
                        d_dist = 1.27 * hXA
                        d_price = A.price - d_dist if direction == "Bullish" else A.price + d_dist
                        predicted_D = Point(0, d_price, 0)
                        patterns.append(Pattern("Butterfly (Potential)", direction, [X, A, B, C, predicted_D], 0))
                    
                    # Crab Formation Check (XB 0.382-0.618) - overlaps with Gartley/Bat roughly
                    # But Crab is specifically for deep extension (1.618)
                    if (0.382*(1-err) <= r_xb <= 0.618*(1+err)) and (0.382 <= r_ac <= 0.886):
                         # If it matches Gartley/Bat, we might list both or pick best fit.
                         # Just adding as Potential Crab for now if ratio is broad
                         d_dist = 1.618 * hXA
                         d_price = A.price - d_dist if direction == "Bullish" else A.price + d_dist
                         predicted_D = Point(0, d_price, 0)
                         patterns.append(Pattern("Crab (Potential)", direction, [X, A, B, C, predicted_D], 0))

        return patterns

    def analyze(self, klines_data: List[List[Any]], tolerance: float = None) -> List[Dict[str, Any]]:
        # klines format: [time, open, high, low, close, ...]
        if not klines_data:
            return []
            
        df = pd.DataFrame(klines_data, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'close_time', 'qav', 'num_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
        # Convert necessary columns to float
        for col in ['high', 'low', 'close', 'open']:
            df[col] = df[col].astype(float)
        
        # Determine pivot order based on data length
        # Using a smaller order allows identifying smaller/local patterns
        # With 1000 candles, order=5 is fine
        order = 5 
            
        points = self.find_peaks_troughs(df, order=order)
        patterns = self.find_patterns(points, tolerance=tolerance)
        
        # Format for output
        results = []
        for p in patterns:
            # We want to keep only the most recent ones or all? user said "Identify", usually all visible.
            
            pts_data = []
            for pt in p.points:
                pts_data.append({
                    'index': pt.index,
                    'price': pt.price,
                    'time': pt.time
                })
            
            results.append({
                'name': p.name,
                'direction': p.direction,
                'points': pts_data
            })
            
        return results

pattern_recognizer = HarmonicPatternRead()
