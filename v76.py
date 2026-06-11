import streamlit as st
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import os, sys, contextlib

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "source": "yahoo"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v134", layout="wide")

@contextlib.contextmanager
def mute_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        if 'c' not in df.columns: df['c'] = df['Close']
            
        df['ma10'] = df['c'].rolling(10).mean()
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=1).mean()
        
        delta = df['c'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        # RSI chuẩn TradingView (EMA alpha=1/14)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (FULL KHUNG)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

@st.cache_data(ttl=60)
def fetch_master_data(name, symbol, source, tf):
    try:
        # A. XỬ LÝ VN-INDEX QUA VNSTOCK (NGUỒN VCI)
        if source == "vnstock":
            with mute_stdout():
                q = Quote(symbol=symbol, source='VCI')
                # Tải lịch sử 1D cực dài để gộp cho 1w, 1m, 3m
                if any(x in tf for x in ['d', 'w', 'm']):
                    df = q.history(start='2010-01-01', interval='1D')
                    if tf == '3d': df = resample_ohlc(df.set_index('time'), '3D').reset_index()
                    elif tf == '1w': df = resample_ohlc(df.set_index('time'), 'W-MON').reset_index()
                    elif tf == '1m': df = resample_ohlc(df.set_index('time'), 'ME').reset_index()
                    elif tf == '3m': df = resample_ohlc(df.set_index('time'), '3ME').reset_index()
                else: # Khung 1h, 4h, 8h...
                    df = q.history(start=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'), interval='1H')
                    if tf != '1h': df = resample_ohlc(df.set_index('time'), tf.upper()).reset_index()
                
                df = df.rename(columns={'time':'ts','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
                return calculate_indicators(df)

        # B. BITCOIN & VÀNG QUA YAHOO (FIX LẶP GIÁ)
        else:
            if 'm' in tf and '1m' not in tf: # 15m, 30m
                df = yf.download(symbol, period='7d', interval=tf, progress=False)
            elif any(x in tf for x in ['h', 'H']): # 1h, 2h, 4h, 8h, 12h
                df = yf.download(symbol, period='730d', interval='1h', progress=False)
                if tf != '1h': df = resample_ohlc(df, tf.upper())
            else: # 1d, 3d, 1w, 1m, 3m
                df = yf.download(symbol, period='max', interval='1d', progress=False)
                if tf != '1d':
                    rule = {'3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}[tf]
                    df = resample_ohlc(df, rule)

            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    if val == "YẾU": return 'color: #f1c40f; font-weight: bold'
    return ''

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v134</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ dữ liệu {asset['name']}...", expanded=True) as status:
            data_rows, sync_list = [], []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # Chặn khung phút cho VN-INDEX
                if asset['name'] == "VN-INDEX" and 'm' in tf: continue
                
                df = fetch_data_v119(asset['name'], asset['symbol'], asset['source'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = float(last['Close'])
                    if asset_price == 0: asset_price = p_val
                    
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
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
                    
                    sync_list.append({"tf": tf, "code": r_code})
                    def sign(v1, v2): return "TĂNG" if v1 > v2 else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": sign(p_val, float(last['ma20'])),
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": sign(p_val, float(last['ma50'])),
                        "MA 10/20": sign(float(last['ma10']), float(last['ma20'])),
                        "RSI": int(r),
                        "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
