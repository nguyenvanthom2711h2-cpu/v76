import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Spot)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Đầy đủ 12 khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v128", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        # Tính MA (SMA)
        df['ma10'] = df['Close'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        # RSI Wilder's (RMA) chuẩn 100%
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU "BIG DATA" (FIX THIẾU KHUNG)
# ==========================================
@st.cache_data(ttl=60)
def fetch_master_data(symbol, group):
    """Tải dữ liệu mồi khối lượng lớn để gộp nến không bị lỗi NaN"""
    try:
        if group == "intraday": # Cho 15m, 30m
            df = yf.download(symbol, period='7d', interval='15m', progress=False)
        elif group == "hourly": # Cho 1h -> 12h
            df = yf.download(symbol, period='730d', interval='1h', progress=False)
        else: # Cho 1d -> 3m
            df = yf.download(symbol, period='max', interval='1d', progress=False)
            
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return df
    except: return None

def get_timeframe_data(master_dfs, tf):
    """Gộp nến từ dữ liệu mồi chính xác"""
    try:
        rule_map = {
            '15m':'15min', '30m':'30min', '1h':'1h', '2h':'2H', '4h':'4H', 
            '8h':'8H', '12h':'12H', '1d':'1D', '3d':'3D', '1w':'W-MON', 
            '1m':'ME', '3m':'3ME'
        }
        
        # Chọn nguồn dữ liệu mồi
        if '15m' in tf or '30m' in tf: source_df = master_dfs['intraday']
        elif 'h' in tf or 'H' in tf: source_df = master_dfs['hourly']
        else: source_df = master_dfs['daily']
        
        if source_df is None: return None
        
        # Resample
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        resampled = source_df.resample(rule_map[tf]).agg(logic).dropna()
        
        return calculate_indicators(resampled)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v128</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật thực: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Tải dữ liệu mồi cho tài sản này
        master_dfs = {
            "intraday": fetch_master_data(asset['symbol'], "intraday"),
            "hourly": fetch_master_data(asset['symbol'], "hourly"),
            "daily": fetch_master_data(asset['symbol'], "daily")
        }
        
        # Lấy giá HT từ nến 15m mới nhất
        live_p = 0
        if master_dfs["intraday"] is not None:
            live_p = float(master_dfs["intraday"]['Close'].iloc[-1])
        
        p_title = f"{live_p:,.1f}" if live_p > 0 else "---"
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {p_title}", expanded=True):
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung giờ/phút
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h']): continue
                
                df_ind = get_timeframe_data(master_dfs, tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = last['Close']
                    r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r > r45 and r < r9: r_stat, r_code = "CHỈNH (-)", 0
                    elif r < r45 and r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                        elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                    
                    sync_list.append({"code": r_code})
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p_val > last['ma20'] else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                st.error(f"❌ {asset['name']} hiện đang mất kết nối dữ liệu.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
