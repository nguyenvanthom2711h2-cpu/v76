import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings
import pytz
from scipy.signal import argrelextrema

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

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m']

st.set_page_config(page_title="Master Trade v148 - Phân kỳ RSI", layout="wide")

# ==========================================
# 2. THUẬT TOÁN PHÂN KỲ & CHỈ BÁO
# ==========================================
def detect_rsi_divergence(df, order=5):
    """
    Nhận diện Phân kỳ (Bearish) và Hội tụ (Bullish) RSI
    order: số nến xung quanh để xác định một đỉnh/đáy (mặc định 5)
    """
    if len(df) < 30: return "-"
    
    # Tìm các vị trí đỉnh/đáy của Giá và RSI
    # Đỉnh (Peaks)
    high_indices = argrelextrema(df['High'].values, np.greater, order=order)[0]
    # Đáy (Troughs)
    low_indices = argrelextrema(df['Low'].values, np.less, order=order)[0]

    # Kiểm tra Hội tụ (Bullish Divergence) - Đáy
    if len(low_indices) >= 2:
        i2, i1 = low_indices[-2], low_indices[-1] # i1 là đáy gần nhất
        # Giá tạo đáy thấp hơn (LL) nhưng RSI tạo đáy cao hơn (HL)
        if df['Low'].iloc[i1] < df['Low'].iloc[i2] and df['rsi_val'].iloc[i1] > df['rsi_val'].iloc[i2]:
            # Kiểm tra xem đáy này có phải xuất hiện gần đây không (trong vòng 10 nến)
            if (len(df) - 1 - i1) < 10:
                return "HỘI TỤ (MUA) 🚀"

    # Kiểm tra Phân kỳ (Bearish Divergence) - Đỉnh
    if len(high_indices) >= 2:
        i2, i1 = high_indices[-2], high_indices[-1]
        # Giá tạo đỉnh cao hơn (HH) nhưng RSI tạo đỉnh thấp hơn (LH)
        if df['High'].iloc[i1] > df['High'].iloc[i2] and df['rsi_val'].iloc[i1] < df['rsi_val'].iloc[i2]:
            if (len(df) - 1 - i1) < 10:
                return "PHÂN KỲ (BÁN) 📉"

    return "-"

def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        col = 'Close'
        # Tính MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # Tính RSI chuẩn Wilder's
        delta = df[col].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        
        # Thêm cột Phân kỳ vào dòng cuối cùng
        df['div_status'] = detect_rsi_divergence(df)
        
        return df
    except:
        return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU
# ==========================================
def fetch_data_v148(symbol, tf):
    try:
        if tf in ['15m', '30m']: f_tf, p = tf, '5d'
        elif tf in ['1h', '2h', '4h', '8h', '12h']: f_tf, p = '1h', '730d'
        else: f_tf, p = '1d', 'max'
            
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=15)
        if df.empty: return None
        
        # Gộp nến cho các khung đặc thù
        rule_map = {
            '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', 
            '3d':'3D', '1w':'W-MON', '1m':'ME'
        }
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN & HIỂN THỊ
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)", "HỘI TỤ (MUA) 🚀"]: return 'background-color: #004d26; color: #00ff88; font-weight: bold;'
    if val in ["GIẢM", "CHỈNH (-)", "PHÂN KỲ (BÁN) 📉"]: return 'background-color: #4d0000; color: #ff4444; font-weight: bold;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v148</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_placeholder = st.empty()
            table_placeholder = st.empty()
            
            with st.spinner(f"Đang phân tích {asset['name']}..."):
                data_rows = []
                for tf in TIMEFRAMES:
                    # Bỏ qua intraday cho VN-INDEX
                    if asset['symbol'] == "^VNINDEX" and any(x in tf for x in ['m', 'h']):
                        continue
                    
                    df_ind = fetch_data_v148(asset['symbol'], tf)
                    if df_ind is not None and len(df_ind) > 0:
                        last = df_ind.iloc[-1]
                        p_val = float(last['Close'])
                        
                        # RSI Logic
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        if r > r9 and r > r45: r_stat = "TĂNG"
                        elif r < r9 and r < r45: r_stat = "GIẢM"
                        elif r9 > r > r45: r_stat = "CHỈNH (-)"
                        elif r45 > r > r9: r_stat = "HỒI (+)"
                        else: r_stat = "YẾU"
                        
                        # MA Logic
                        wave = "TĂNG" if p_val > last['ma20'] else "GIẢM"

                        data_rows.append({
                            "KHUNG": tf.upper(), 
                            "XU HƯỚNG": wave, 
                            "RSI (9/45)": r_stat,
                            "PHÂN KỲ RSI": last['div_status'],
                            "GIÁ": f"{p_val:,.1f}",
                            "RSI": int(r)
                        })

                if data_rows:
                    status_placeholder.success(f"💠 {asset['name']} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    df_display = pd.DataFrame(data_rows)
                    table_placeholder.table(df_display.style.map(style_text))
                else:
                    status_placeholder.error(f"❌ {asset['name']}: Yahoo Finance không trả về dữ liệu.")

    # Tự động reload sau 5 phút để tránh bị Yahoo block
    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
