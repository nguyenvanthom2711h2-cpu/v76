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

# 12 Khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v147", layout="wide")

# ==========================================
# 2. THUẬT TOÁN RSI & MA
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        col = 'Close'
        # Tính MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # Tính RSI chuẩn Wilder's (RMA)
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
# 3. TRUY XUẤT & GỘP NẾN CHUẨN
# ==========================================
def fetch_data_v147(symbol, tf):
    try:
        # Tối ưu hóa Interval để Yahoo không chặn
        if tf in ['15m', '30m']: 
            f_tf, p = tf, '5d'
        elif tf in ['1h', '2h', '4h', '8h', '12h']: 
            f_tf, p = '1h', '730d' # Lấy nến 1h làm gốc để gộp
        else: 
            f_tf, p = '1d', 'max' # Lấy nến 1d làm gốc
            
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=15)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)

        # Logic gộp nến (Resample) cho các khung không có sẵn
        rule_map = {
            '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', 
            '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'
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
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88;'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v147</h2>", unsafe_allow_html=True)
    
    # Tạo Tabs cho từng tài sản để tránh load quá nặng 1 lúc
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_placeholder = st.empty()
            table_placeholder = st.empty()
            
            with st.spinner(f"Đang quét {asset['name']}..."):
                data_rows = []
                for tf in TIMEFRAMES:
                    # KHẮC PHỤC VN-INDEX: Yahoo ko có intraday cho ^VNINDEX
                    if asset['symbol'] == "^VNINDEX" and any(x in tf for x in ['m', 'h']):
                        continue
                    
                    df_ind = fetch_data_v147(asset['symbol'], tf)
                    if df_ind is not None and len(df_ind) > 0:
                        last = df_ind.iloc[-1]
                        p_val = float(last['Close'])
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        
                        # Logic RSI
                        if r > r9 and r > r45: r_stat = "TĂNG"
                        elif r < r9 and r < r45: r_stat = "GIẢM"
                        elif r9 > r > r45: r_stat = "CHỈNH (-)"
                        elif r45 > r > r9: r_stat = "HỒI (+)"
                        else: r_stat = "YẾU"
                        
                        # Logic MA
                        wave = "TĂNG" if p_val > last['ma20'] else "GIẢM"
                        p50 = "TĂNG" if p_val > last['ma50'] else "GIẢM"
                        m1020 = "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM"

                        data_rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": wave, 
                            "RSI 9/45": r_stat,
                            "Giá/MA50": p50, 
                            "MA 10/20": m1020,
                            "RSI": int(r), 
                            "Giá": f"{p_val:,.1f}"
                        })

                if data_rows:
                    status_placeholder.success(f"💠 {asset['name']} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_placeholder.table(pd.DataFrame(data_rows).style.map(style_text))
                else:
                    status_placeholder.error(f"❌ {asset['name']}: Yahoo Finance không cung cấp dữ liệu khung này.")

    # Auto-refresh mỗi 5 phút (tránh bị Yahoo khóa IP nếu refresh quá nhanh)
    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
