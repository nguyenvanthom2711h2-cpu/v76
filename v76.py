import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import requests
import warnings

# Tắt cảnh báo
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "type": "crypto"},
    {"name": "VÀNG", "symbol": "GC=F", "type": "commodity"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "type": "index"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Trade Master v94", layout="wide")

# ==========================================
# 2. HÀM LẤY DỮ LIỆU VN-INDEX TỪ SSI (DỰ PHÒNG CAO)
# ==========================================
def fetch_vnindex_direct(tf):
    """Lấy dữ liệu VN-Index trực tiếp từ API tài chính Việt Nam để tránh bị Yahoo chặn"""
    try:
        # Giả lập lấy dữ liệu từ nguồn SSI/CafeF
        res_map = '1' if 'h' in tf else 'D'
        url = f"https://api.vstock.top/api/quote/history?symbol=VNINDEX&resolution={res_map}&from={int((datetime.now()-timedelta(days=365)).timestamp())}&to={int(datetime.now().timestamp())}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data and 'c' in data:
            df = pd.DataFrame({
                'ts': data['t'], 'o': data['o'], 'h': data['h'], 'l': data['l'], 'c': data['c'], 'v': data['v']
            })
            df['ts'] = pd.to_datetime(df['ts'], unit='s')
            return df
        return None
    except:
        return None

# ==========================================
# 3. HÀM TẢI DỮ LIỆU TOÀN CẦU (YAHOO)
# ==========================================
@st.cache_data(ttl=300) # Lưu dữ liệu 5 phút để tránh bị chặn IP
def get_global_data(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        fetch_tf = yf_map.get(tf, '1h' if 'h' in tf else '1d')
        
        # Logic period chuẩn để tránh lỗi Yahoo
        if fetch_tf == '1h': period = '730d'
        else: period = 'max'

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=15)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df = df.reset_index()
        df = df.rename(columns={df.columns[0]:'ts', 'Open':'o', 'High':'h', 'Low':'l', 'Close':'c', 'Volume':'v'})
        
        # Xử lý gộp nến 4h
        if tf == '4h':
            df['ts'] = pd.to_datetime(df['ts'])
            df = df.set_index('ts').resample('4H').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
        
        return df
    except:
        return None

# ==========================================
# 4. TÍNH TOÁN CHỈ BÁO
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma20'] = df['c'].rolling(window=20).mean()
        df['ma50'] = df['c'].rolling(window=50, min_periods=10).mean()
        
        delta = df['c'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=5).mean()
        return df
    except: return None

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ff88;'>🏆 Master Trade Dashboard v94</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Cập nhật thực: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.expander(f"💠 {asset['name']}", expanded=True):
            data_rows = []
            
            for tf in TIMEFRAMES:
                # Ưu tiên lấy VNINDEX từ nguồn trực tiếp
                if asset['name'] == "VN-INDEX":
                    df_raw = fetch_vnindex_direct(tf)
                    if df_raw is None: # Fallback sang Yahoo
                        df_raw = get_global_data("^VNINDEX", tf)
                else:
                    df_raw = get_global_data(asset['symbol'], tf)
                
                df = calculate_indicators(df_raw)
                
                if df is not None:
                    last = df.iloc[-1]
                    p, r, r9, r45, m20 = last['c'], last['rsi'], last['rsi9'], last['rsi45'], last['ma20']
                    
                    if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                    elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                    else: r_stat = "🟡 YẾU"
                    
                    wave = "🟢 TĂNG" if p > m20 else "🔴 GIẢM"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "GIÁ HIỆN TẠI": f"{p:,.1f}",
                        "RSI": int(r)
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.error(f"❌ Đang mất kết nối dữ liệu cho {asset['name']}. Hệ thống đang thử lại nguồn dự phòng...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
