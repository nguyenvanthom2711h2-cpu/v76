import streamlit as st
import ccxt
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
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
    {"name": "BITCOIN", "symbol": "BTC/USDT", "yf_symbol": "BTC-USD", "source": "binance"},
    {"name": "VÀNG", "symbol": "GC=F", "yf_symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "yf_symbol": "^VNINDEX", "source": "vnstock"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v111", layout="wide")
exchange = ccxt.binance({'timeout': 15000, 'enableRateLimit': True})

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RSI RMA & MA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        df['ma20'] = df['c'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['c'].rolling(window=50, min_periods=1).mean()
        
        delta = df['c'].diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (FIX VNINDEX & BTC)
# ==========================================
def resample_ohlc(df, rule):
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    logic = {'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}
    return df.resample(rule).agg(logic).dropna().reset_index()

@st.cache_data(ttl=30)
def fetch_data(asset, tf):
    try:
        # A. XỬ LÝ VN-INDEX (Nguồn SSI cực chuẩn)
        if asset['source'] == "vnstock":
            q = Quote(symbol='VNINDEX', source='SSI') # Dùng nguồn SSI nội địa
            # Lấy nến 1H cho khung giờ, 1D cho khung ngày
            v_tf = '1H' if 'h' in tf.lower() else '1D'
            df = q.history(start='2020-01-01', interval=v_tf)
            if df is None or df.empty: return None
            df = df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
            
            # Gộp nến cho các khung trung gian
            rule_map = {'4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
            if tf in rule_map: df = resample_ohlc(df, rule_map[tf])
            return calculate_indicators(df)

        # B. XỬ LÝ BITCOIN (Binance -> Yahoo)
        if asset['name'] == "BITCOIN":
            try:
                # Tải từ Binance
                limit = 1000 if tf in ['1w', '1M'] else 500
                bars = exchange.fetch_ohlcv(asset['symbol'], timeframe=tf if tf != '3M' else '1M', limit=limit)
                df = pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
                if tf == '3M': df = resample_ohlc(df, '3ME')
                return calculate_indicators(df)
            except:
                # Fallback sang Yahoo nếu bị chặn IP
                symbol = asset['yf_symbol']
                yf_tf = '1h' if 'h' in tf else '1d'
                df_yf = yf.download(symbol, period='max', interval=yf_tf, progress=False)
                df_yf = df_yf.reset_index().rename(columns={df_yf.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c'})
                return calculate_indicators(df_yf)

        # C. CÁC TÀI SẢN KHÁC (VÀNG)
        if asset['source'] == "yahoo":
            yf_tf = '1h' if 'h' in tf else '1d'
            df = yf.download(asset['symbol'], period='max', interval=yf_tf, progress=False)
            df = df.reset_index().rename(columns={df.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c'})
            if tf == '4h': df = resample_ohlc(df, '4H')
            return calculate_indicators(df)

    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v111</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        st.subheader(f"💠 {asset['name']}")
        data_rows = []
        sync_list = []
        
        for tf in TIMEFRAMES:
            # Chặn khung phút cho VN-INDEX
            if asset['name'] == "VN-INDEX" and 'm' in tf: continue
            
            df = fetch_data(asset, tf)
            if df is not None:
                last = df.iloc[-1]
                p, r, r9, r45 = last['c'], last['rsi'], last['rsi9'], last['rsi45']
                
                # Trạng thái RSI
                if r > r9 and r > r45: r_stat, r_code = "🟢 TĂNG", 1
                elif r < r9 and r < r45: r_stat, r_code = "🔴 GIẢM", -1
                elif r9 > r > r45: r_stat, r_code = "🟠 CHỈNH (-)", 0
                elif r45 > r > r9: r_stat, r_code = "🔵 HỒI (+)", 0
                else: r_stat, r_code = "🟡 YẾU", 0
                
                # Xét đồng thuận (↑) (↓)
                agreement = "-"
                if sync_list:
                    prev = sync_list[-1]
                    if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                    elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                
                sync_list.append({"code": r_code})
                wave = "🟢 TĂNG" if p > last['ma20'] else "🔴 GIẢM"
                
                data_rows.append({
                    "KHUNG": tf.upper(),
                    "SÓNG": wave,
                    "ĐỒNG THUẬN": agreement,
                    "RSI 9/45": r_stat,
                    "RSI": int(r),
                    "GIÁ": f"{p:,.1f}"
                })
        
        if data_rows:
            st.table(pd.DataFrame(data_rows))
        else:
            st.warning(f"🔄 Đang kết nối nguồn dữ liệu {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
