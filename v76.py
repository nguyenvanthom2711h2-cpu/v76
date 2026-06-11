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
import os, sys, contextlib

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC/USDT", "source": "binance"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]
TIMEFRAMES = ['1h', '4h', '8h', '12h', '1d', '3d', '1w', '1m']

st.set_page_config(page_title="Pro Trade Dashboard v139", layout="wide")

@contextlib.contextmanager
def mute_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Đảm bảo cột Close phẳng 1 chiều
        if 'Close' in df.columns: df['c'] = df['Close']
        if isinstance(df['c'], pd.DataFrame): df['c'] = df['c'].iloc[:, 0]
            
        df['ma20'] = df['c'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=1).mean()
        df['ma10'] = df['c'].rolling(10, min_periods=1).mean()
        
        delta = df['c'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        # RSI Wilder's (RMA)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA NGUỒN (ANTI-BLOCK)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'o':'first','h':'max','l':'min','c':'last','v':'sum'}
    # Map đúng tên cột cho Binance/Yahoo
    df_mapped = df.rename(columns={'Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
    return df_mapped.resample(rule).agg(logic).dropna()

@st.cache_data(ttl=60)
def fetch_master_v139(name, symbol, source, tf):
    try:
        # --- A. BITCOIN (BINANCE - Không bao giờ bị chặn) ---
        if source == "binance":
            exchange = ccxt.binance({'timeout': 15000})
            limit = 1000 if tf in ['1w', '1m'] else 500
            bars = exchange.fetch_ohlcv(symbol, timeframe='1d' if any(x in tf for x in ['d', 'w', 'm']) else '1h', limit=limit)
            df = pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df.set_index('ts', inplace=True)
            df = df.rename(columns={'o':'Open','h':'High','l':'Low','c':'Close','v':'Volume'})
            
        # --- B. VN-INDEX (VNSTOCK SSI - Nội địa ổn định) ---
        elif source == "vnstock":
            with mute_stdout():
                q = Quote(symbol=symbol, source='SSI')
                v_tf = '1D' if any(x in tf for x in ['d', 'w', 'm']) else '1H'
                df = q.history(start='2018-01-01', interval=v_tf)
                df = df.rename(columns={'time':'ts','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
                df.set_index('ts', inplace=True)

        # --- C. VÀNG (YAHOO - Có giả lập trình duyệt) ---
        else:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36'})
            f_tf = '1h' if 'h' in tf else '1d'
            p = '730d' if f_tf == '1h' else 'max'
            df = yf.download(symbol, period=p, interval=f_tf, session=session, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        if df is None or df.empty: return None

        # Gộp nến cho các khung trung gian
        rule_map = {'4h':'4H', '8h':'8H', '12h':'12H', '3d':'3D', '1w':'W-MON', '1m':'ME'}
        if tf in rule_map:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN VÀ TÍN HIỆU
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v139</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Dữ liệu đồng bộ lúc: {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                df_ind = fetch_master_v139(asset['name'], asset['symbol'], asset['source'], tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = float(last['c'])
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
                        key = f"{asset['name']}_{prev['tf']}_{tf}"
                        if r_code == 1 and prev['code'] == 1:
                            agreement = "MUA (↑)"
                            if last_alerts.get(key) != "BUY":
                                try: bot.send_message(CHAT_ID, f"🚀 **ĐỒNG THUẬN MUA: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "BUY"
                        elif r_code == -1 and prev['code'] == -1:
                            agreement = "BÁN (↓)"
                            if last_alerts.get(key) != "SELL":
                                try: bot.send_message(CHAT_ID, f"🔻 **ĐỒNG THUẬN BÁN: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "SELL"
                        else: last_alerts[key] = "NONE"

                    sync_list.append({"tf": tf, "code": r_code})
                    def sign(v1, v2): return "TĂNG" if v1 > v2 else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(), "Sóng": "TĂNG" if p_val > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement, "RSI 9/45": r_stat,
                        "P/MA50": sign(p_val, float(last['ma50'])), "MA 10/20": sign(float(last['ma10']), float(last['ma20'])),
                        "RSI": int(r), "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} mất kết nối.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
