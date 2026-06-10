import streamlit as st
import ccxt
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
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
    {"name": "BITCOIN", "symbol": "BTC-USD", "source": "yahoo"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']
WAIT_TIME = 60 

last_alerts = {}
last_terminal_state = {}

st.set_page_config(page_title="Pro Trade Dashboard v123", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Chuẩn hóa tên cột
        if 'c' not in df.columns:
            if 'Close' in df.columns: df['c'] = df['Close']
            else: return None
            
        df['ma10'] = df['c'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['c'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=1).mean()
        
        delta = df['c'].diff()
        avg_gain = (delta.clip(lower=0)).ewm(alpha=1/14, adjust=False).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

def resample_ohlc(df, rule):
    try:
        df = df.copy()
        df['ts'] = pd.to_datetime(df['ts'])
        df.set_index('ts', inplace=True)
        logic = {'o':'first','h':'max','l':'min','c':'last','v':'sum'}
        # Lọc các cột có sẵn
        logic = {k: v for k, v in logic.items() if k in df.columns or k.upper() in df.columns}
        return df.resample(rule).agg(logic).dropna().reset_index()
    except: return None

# ==========================================
# 3. LẤY DỮ LIỆU ĐA TẦNG (FIX VN-INDEX & LẶP GIÁ)
# ==========================================
@st.cache_data(ttl=30)
def fetch_data(name, symbol, source, tf):
    try:
        # --- A. VN-INDEX (Chiến lược 3 lớp) ---
        if name == "VN-INDEX":
            # Yahoo VN-Index ko có nến phút/giờ, ép về nến ngày
            if any(x in tf for x in ['m', 'h', 'H']): return None
            
            # Thử lớp 1: SSI
            try:
                df = Quote(symbol=symbol, source='SSI').history(start='2015-01-01', interval='1D')
                if df is not None and not df.empty:
                    df = df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
                    if tf != '1d': 
                        df = resample_ohlc(df, {'3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}[tf])
                    return calculate_indicators(df)
            except: pass

            # Thử lớp 2: Yahoo (Ticker quốc tế)
            df_yf = yf.download('^VNINDEX', period='max', interval='1d', progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf = df_yf.reset_index().rename(columns={df_yf.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
                if tf != '1d':
                    df_yf = resample_ohlc(df_yf, {'3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}.get(tf, '1D'))
                return calculate_indicators(df_yf)
            return None

        # --- B. BITCOIN & VÀNG (Fix lặp giá Yahoo) ---
        else:
            # Chọn interval và period chuẩn để Yahoo ko trả về nến giờ cho yêu cầu nến phút
            if 'm' in tf: interval, period = tf, '5d'
            elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): interval, period = '1h', '730d'
            else: interval, period = '1d', 'max'

            # Giả lập trình duyệt để tránh bị chặn
            headers = {'User-Agent': 'Mozilla/5.0'}
            df_raw = yf.download(symbol, period=period, interval=interval, progress=False)
            
            if df_raw.empty: return None
            if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
            df = df_raw.reset_index().rename(columns={df_raw.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})

            # Gộp nến cho các khung đặc thù
            rule_map = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
            if tf in rule_map and tf != interval:
                df = resample_ohlc(df, rule_map[tf])
            
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v123</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            data_rows, sync_list = [], []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                df = fetch_data(asset['name'], asset['symbol'], asset['source'], tf)
                if df is not None and not df.empty:
                    last = df.iloc[-1]
                    p = float(last['c'])
                    if asset_price == 0: asset_price = p
                    
                    r, r9, r45 = float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                    
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        key = f"{asset['name']}_{prev['tf']}_{tf}"
                        if r_code == 1 and prev['code'] == 1:
                            agreement = "MUA (↑)"
                            if last_alerts.get(key) != "BUY":
                                try: bot.send_message(CHAT_ID, f"🚀 **ĐỒNG THUẬN MUA: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "BUY"
                        elif r_code == -1 and prev['code'] == -1:
                            agreement = "BÁN (↓)"
                            if last_alerts.get(key) != "SELL":
                                try: bot.send_message(CHAT_ID, f"🔻 **ĐỒNG THUẬN BÁN: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "SELL"
                        else: last_alerts[key] = "NONE"

                    sync_list.append({"tf": tf, "code": r_code})
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p > float(last['ma50']) else "GIẢM",
                        "MA 10/20": "TĂNG" if float(last['ma10']) > float(last['ma20']) else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} lỗi kết nối.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
