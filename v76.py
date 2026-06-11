import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz
import requests

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "alt": "BTC-USD"},
    {"name": "VÀNG", "symbol": "XAUUSD=X", "alt": "GC=F"}, # Nếu Spot lỗi dùng Futures
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "alt": "VNINDEX.VN"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Trade Dashboard v129", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # SMA 10, 20, 50
        df['ma10'] = df['Close'].rolling(10).mean()
        df['ma20'] = df['Close'].rolling(20).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        # RSI Wilder's chuẩn (RMA)
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
# 3. MÁY TẢI DỮ LIỆU ĐA TẦNG (ANTI-BLOCK)
# ==========================================
@st.cache_data(ttl=60)
def fetch_raw_data(symbol, tf_group):
    """Tải dữ liệu mồi tách biệt để tránh lặp giá và chặn IP"""
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    try:
        if tf_group == "short": # 15m - 30m
            df = yf.download(symbol, period='5d', interval='15m', session=session, progress=False)
        elif tf_group == "mid": # 1h -> 12h
            df = yf.download(symbol, period='730d', interval='1h', session=session, progress=False)
        else: # 1d -> 3m
            df = yf.download(symbol, period='max', interval='1d', session=session, progress=False)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def process_frame(master_data, tf):
    """Gộp nến từ dữ liệu mồi chính xác cho từng khung"""
    try:
        rule_map = {
            '15m':'15min', '30m':'30min', '1h':'1h', '2h':'2H', '4h':'4H', 
            '8h':'8H', '12h':'12H', '1d':'1D', '3d':'3D', '1w':'W-MON', 
            '1m':'ME', '3m':'3ME'
        }
        group = "short" if 'm' in tf else ("mid" if 'h' in tf or 'H' in tf else "long")
        df = master_data[group].copy()
        
        if tf not in ['15m', '1h', '1d']:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v129</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Tải dữ liệu mồi (Thử mã chính, nếu lỗi thử mã phụ)
        with st.spinner(f"Đang đồng bộ {asset['name']}..."):
            master = {
                "short": fetch_raw_data(asset['symbol'], "short"),
                "mid": fetch_raw_data(asset['symbol'], "mid"),
                "long": fetch_raw_data(asset['symbol'], "long")
            }
            # Fallback nếu mã chính bị chặn
            if master["long"] is None:
                master = {
                    "short": fetch_raw_data(asset['alt'], "short"),
                    "mid": fetch_raw_data(asset['alt'], "mid"),
                    "long": fetch_raw_data(asset['alt'], "long")
                }

        if master["long"] is not None:
            live_p = float(master["mid" if master["mid"] is not None else "long"]['Close'].iloc[-1])
            with st.expander(f"💠 {asset['name']} | Giá Hiện Tại: {live_p:,.1f}", expanded=True):
                data_rows = []
                sync_list = []
                for tf in TIMEFRAMES:
                    # VN-Index bỏ qua khung giờ/phút
                    if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                    
                    df_ind = process_frame(master, tf)
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        p_val, r, r9, r45 = last['Close'], last['rsi_val'], last['rsi9'], last['rsi45']
                        
                        # Logic Trạng thái
                        if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                        elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                        elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                        elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
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
                            "RSI": int(r),
                            "Giá": f"{p_val:,.1f}"
                        })
                
                if data_rows:
                    st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50']))
        else:
            st.error(f"❌ {asset['name']} đang mất kết nối dữ liệu. Vui lòng chờ Yahoo Finance mở khóa IP.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
