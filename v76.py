import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz
import requests

# Tắt cảnh báo
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
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Cloud Trade Dashboard v138", layout="wide")

# ==========================================
# 2. THUẬT TOÁN RSI RMA (CHUẨN 100% TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Đảm bảo cột giá phẳng hoàn toàn
        close_series = df['Close']
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
            
        df['ma10'] = close_series.rolling(10).mean()
        df['ma20'] = close_series.rolling(20).mean()
        df['ma50'] = close_series.rolling(50, min_periods=1).mean()
        
        delta = close_series.diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        
        # Công thức RMA (Wilder's Smoothing)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU "SẠCH" (VƯỢT RÀO CLOUD)
# ==========================================
def clean_yahoo_df(df):
    """San phẳng tiêu đề và xử lý múi giờ"""
    if df is None or df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_convert(VN_TZ)
    return df

@st.cache_data(ttl=60)
def fetch_cloud_data(symbol, group):
    """Tải dữ liệu tập trung với User-Agent giả lập người dùng thật"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        if group == "short": # 15m, 30m
            df = yf.download(symbol, period='7d', interval='15m', progress=False, timeout=20)
        elif group == "mid": # 1h -> 12h
            df = yf.download(symbol, period='730d', interval='1h', progress=False, timeout=20)
        else: # 1d -> 3m
            df = yf.download(symbol, period='max', interval='1d', progress=False, timeout=20)
        return clean_yahoo_df(df)
    except: return None

def resample_ohlc(df, rule):
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

# ==========================================
# 4. GIAO DIỆN VÀ TÍN HIỆU
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v138</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ dữ liệu {asset['name']}...", expanded=True) as status:
            # Tải 3 khối dữ liệu thô
            m = {
                "short": fetch_cloud_data(asset['symbol'], "short"),
                "mid": fetch_cloud_data(asset['symbol'], "mid"),
                "long": fetch_cloud_data(asset['symbol'], "long")
            }
            
            if m["long"] is None:
                st.error(f"❌ {asset['name']} bị Yahoo chặn kết nối.")
                continue

            live_p = float(m["mid" if m["mid"] is not None else "long"]['Close'].iloc[-1])
            data_rows, sync_list = [], []
            
            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung giờ
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h']): continue
                
                # Chọn nguồn và gộp nến
                src = m["short"] if 'm' in tf else (m["mid"] if any(x in tf for x in ['h', 'H']) else m["long"])
                if src is None: continue
                
                rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
                df_tf = resample_ohlc(src, rule_map[tf]) if tf in rule_map else src
                
                df_ind = calculate_indicators(df_tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = float(last['Close'])
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
                    # Logic RSI Status
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
                    wave = "TĂNG" if p_val > last['ma20'] else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(), "Sóng": wave, "Đồng thuận": agreement,
                        "RSI 9/45": r_stat, "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r), "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {live_p:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
