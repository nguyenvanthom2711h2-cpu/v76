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

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']
WAIT_TIME = 60 

last_alerts = {}

@contextlib.contextmanager
def mute_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Đảm bảo cột giá là 1 chiều
        if 'c' not in df.columns and 'Close' in df.columns:
            df['c'] = df['Close']
            
        df['ma20'] = df['c'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['c'].rolling(window=50, min_periods=1).mean()
        
        delta = df['c'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA NGUỒN (FIX VN-INDEX)
# ==========================================
def resample_ohlc(df, rule):
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    logic = {'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}
    return df.resample(rule).agg(logic).dropna().reset_index()

@st.cache_data(ttl=30)
def get_unified_data(asset, tf):
    try:
        # --- NGUỒN VNSTOCK (SSI) CHO VN-INDEX ---
        if asset['source'] == "vnstock":
            with mute_stdout():
                q = Quote(symbol=asset['symbol'], source='SSI')
                v_tf = '1H' if any(x in tf for x in ['m', 'h', 'H']) else '1D'
                # Tải history đủ dài để gộp nến
                start_date = '2020-01-01' if v_tf == '1D' else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
                df = q.history(start=start_date, interval=v_tf)
                if df is None or df.empty: return None
                df = df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
        
        # --- NGUỒN YAHOO CHO BTC & VÀNG ---
        else:
            yf_map = {'15m':'15m','1h':'1h','1d':'1d'}
            fetch_tf = tf if 'm' in tf else ('1h' if any(x in tf for x in ['h', 'H']) else '1d')
            period = '7d' if 'm' in tf else ('730d' if 'h' in fetch_tf else 'max')
            
            with mute_stdout():
                df_raw = yf.download(asset['symbol'], period=period, interval=yf_map.get(fetch_tf, '1d'), progress=False)
            if df_raw.empty: return None
            if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
            df = df_raw.reset_index().rename(columns={df_raw.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})

        # --- LOGIC GỘP NẾN CHUNG ---
        rule_map = {'2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', '3d':'3D', '1w':'W-MON', '1M':'ME', '3M':'3ME'}
        if tf in rule_map:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v113</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Lấy giá hiện tại từ khung 1h hoặc 1d
        df_price = get_unified_data(asset, '1d')
        live_p = float(df_price['c'].iloc[-1]) if df_price is not None else 0
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {live_p:,.2f}", expanded=True):
            data_rows = []
            sync_list = []
            for tf in TIMEFRAMES:
                # Chặn khung quá nhỏ cho VN-INDEX để tránh lag
                if asset['name'] == "VN-INDEX" and 'm' in tf: continue
                
                df = get_unified_data(asset, tf)
                if df is not None:
                    last = df.iloc[-1]
                    p = float(last['c'])
                    r = float(last['rsi'])
                    r9 = float(last['rsi9'])
                    r45 = float(last['rsi45'])
                    m20 = float(last['ma20'])
                    
                    # Trạng thái
                    if r > r9 and r > r45: r_stat, r_code = "🟢 TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "🔴 GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "🟠 CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "🔵 HỒI (+)", 0
                    else: r_stat, r_code = "🟡 YẾU", 0
                    
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

                    sync_list.append({"tf":tf, "code":r_code})
                    wave = "🟢 TĂNG" if p > m20 else "🔴 GIẢM"
                    
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
                st.warning(f"🔄 Đang tải dữ liệu cho {asset['name']}...")

    time.sleep(WAIT_TIME)
    st.rerun()

if __name__ == "__main__":
    main()
