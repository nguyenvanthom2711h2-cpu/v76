import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v151", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (AUTO-CLEAN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 50: return None 
    try:
        df = df.copy()
        # Tìm cột giá đóng cửa bất kể hoa thường hay Multi-Index
        close_col = [c for c in df.columns if 'close' in str(c).lower()]
        if not close_col: return None
        col = close_col[0]
        
        # MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # RSI Wilder's
        delta = df[col].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA NGUỒN V151
# ==========================================
def fetch_data_v151(symbol, tf):
    try:
        # Chặn khung nhỏ cho VN-INDEX
        if symbol == "^VNINDEX" and any(x in tf for x in ['m', 'h', 'H']):
            return None
            
        # Chọn Interval
        if tf in ['15m', '30m']: 
            interval, period = tf, '60d'
        elif any(x in tf for x in ['h', '2h', '4h', '8h', '12h']): 
            interval, period = '1h', '730d' 
        else: 
            interval, period = '1d', '20y' # Ép lấy 20 năm cho Index
            
        # Tải dữ liệu bằng yf.download (ổn định hơn cho ^VNINDEX)
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        
        if df.empty: return None

        # --- XỬ LÝ LỖI CỘT MỚI CỦA YAHOO (QUAN TRỌNG) ---
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Resampling
        rule_map = {
            '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', 
            '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'
        }
        
        if tf in rule_map and tf != interval:
            # Tìm các cột cần thiết cho gộp nến
            cols = {c.lower(): c for c in df.columns}
            logic = {cols['open']:'first', cols['high']:'max', cols['low']:'min', cols['close']:'last', cols['volume']:'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except Exception as e:
        return None

# ==========================================
# 4. GIAO DIỆN HIỂN THỊ
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold;'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v151</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            msg_area = st.empty()
            
            data_rows = []
            with st.spinner(f"Đang phân tích {asset['name']}..."):
                for tf in TIMEFRAMES:
                    df_ind = fetch_data_v151(asset['symbol'], tf)
                    
                    if df_ind is not None and not df_ind.empty:
                        last = df_ind.iloc[-1]
                        
                        # Chỉ lấy khi đã tính được RSI45
                        if pd.isna(last['rsi45']): continue
                        
                        # Xác định cột giá đóng cửa
                        c_col = [c for c in df_ind.columns if 'close' in str(c).lower()][0]
                        p_val = float(last[c_col])
                        r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                        
                        # Phân tích
                        if r > r9 and r > r45: r_stat = "TĂNG"
                        elif r < r9 and r < r45: r_stat = "GIẢM"
                        elif r9 > r > r45: r_stat = "CHỈNH (-)"
                        elif r45 > r > r9: r_stat = "HỒI (+)"
                        else: r_stat = "YẾU"
                        
                        wave = "TĂNG" if p_val > float(last['ma20']) else "GIẢM"
                        p50 = "TĂNG" if p_val > float(last['ma50']) else "GIẢM"
                        m1020 = "TĂNG" if float(last['ma10']) > float(last['ma20']) else "GIẢM"

                        data_rows.append({
                            "KHUNG": tf.upper(), 
                            "SÓNG MA20": wave, 
                            "RSI 9/45": r_stat,
                            "P/MA50": p50, 
                            "MA 10/20": m1020,
                            "RSI": int(r), 
                            "GIÁ": f"{p_val:,.2f}"
                        })

            if data_rows:
                msg_area.success(f"✅ {asset['name']} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                st.table(pd.DataFrame(data_rows).style.map(style_text))
            else:
                msg_area.warning(f"⚠️ {asset['name']}: Yahoo Finance đang chặn hoặc không đủ dữ liệu nến cho khung này.")

    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
