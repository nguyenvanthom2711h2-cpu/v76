import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz

# Thử import vnstock
try:
    from vnstock import stock_historical_data
except ImportError:
    st.error("❌ Lỗi: Chưa tìm thấy thư viện 'vnstock'. Hãy thêm nó vào file requirements.txt trên GitHub.")
    st.stop()

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v153", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 50: return None 
    try:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        col = 'close'
        
        # MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # RSI Wilder's
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
# 3. TRUY XUẤT DỮ LIỆU ĐA NGUỒN (MULTI-FALLBACK)
# ==========================================
def fetch_global_data(symbol, tf):
    try:
        if tf in ['15m', '30m']: interval, period = tf, '60d'
        elif any(x in tf for x in ['h', '2h', '4h', '8h', '12h']): interval, period = '1h', '730d'
        else: interval, period = '1d', 'max'
        
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        rule_map = {'2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
        if tf in rule_map and tf != interval:
            df = df.resample(rule_map[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        
        return calculate_indicators(df)
    except: return None

def fetch_vn_data(tf):
    """Lấy dữ liệu VN-INDEX - Thử lần lượt các nguồn để né chặn IP"""
    if any(x in tf for x in ['m', 'h', 'H']): return None
    
    sources = ['VCI', 'SSI', 'TCBS', 'DNSE']
    df = None
    
    for src in sources:
        try:
            df = stock_historical_data(symbol='VNINDEX', 
                                       start_date='2018-01-01', 
                                       end_date=datetime.now().strftime('%Y-%m-%d'), 
                                       resolution='1D', type='index', source=src)
            if df is not None and not df.empty:
                break # Nếu lấy được dữ liệu thì dừng thử nguồn khác
        except:
            continue
            
    if df is None or df.empty: return None
    
    try:
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        rule_map = {'3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
        if tf in rule_map:
            df = df.resample(rule_map[tf]).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        return calculate_indicators(df)
    except:
        return None

# ==========================================
# 4. GIAO DIỆN
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold;'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v153</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs(["BITCOIN", "VÀNG", "VN-INDEX"])

    # BITCOIN & VÀNG
    assets = [{"n":"BITCOIN","s":"BTC-USD"}, {"n":"VÀNG","s":"GC=F"}]
    for i, asset in enumerate(assets):
        with tabs[i]:
            data_rows = []
            with st.spinner(f"Đang tải {asset['n']}..."):
                for tf in TIMEFRAMES:
                    df = fetch_global_data(asset['s'], tf)
                    if df is not None:
                        last = df.iloc[-1]
                        if pd.isna(last['rsi45']): continue
                        p_val, r, r9, r45 = float(last['close']), float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                        r_stat = "TĂNG" if r>r9 and r>r45 else ("GIẢM" if r<r9 and r<r45 else ("CHỈNH (-)" if r9>r>r45 else ("HỒI (+)" if r45>r>r9 else "YẾU")))
                        data_rows.append({"KHUNG": tf.upper(), "XU HƯỚNG": "TĂNG" if p_val > last['ma20'] else "GIẢM", "RSI 9/45": r_stat, "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", "MA 10/20": "TĂNG" if last['ma10']>last['ma20'] else "GIẢM", "RSI": int(r), "GIÁ": f"{p_val:,.1f}"})
            if data_rows: st.table(pd.DataFrame(data_rows).style.map(style_text))

    # VN-INDEX
    with tabs[2]:
        data_rows_vn = []
        with st.spinner("Đang quét đa nguồn (VCI/SSI/TCBS) cho VN-INDEX..."):
            for tf in ['1d', '3d', '1w', '1m', '3m']:
                df = fetch_vn_data(tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val, r, r9, r45 = float(last['close']), float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    r_stat = "TĂNG" if r>r9 and r>r45 else ("GIẢM" if r<r9 and r<r45 else ("CHỈNH (-)" if r9>r>r45 else ("HỒI (+)" if r45>r>r9 else "YẾU")))
                    data_rows_vn.append({"KHUNG": tf.upper(), "XU HƯỚNG": "TĂNG" if p_val > last['ma20'] else "GIẢM", "RSI 9/45": r_stat, "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", "MA 10/20": "TĂNG" if last['ma10']>last['ma20'] else "GIẢM", "RSI": int(r), "GIÁ": f"{p_val:,.2f}"})
        if data_rows_vn: st.table(pd.DataFrame(data_rows_vn).style.map(style_text))
        else: st.error("❌ VN-INDEX: Tất cả các nguồn dữ liệu (VCI, SSI, TCBS) hiện đang chặn IP của Streamlit. Hãy thử lại sau ít phút.")

    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
