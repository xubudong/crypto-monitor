import ccxt
import pandas as pd
import requests
import os
import time
from datetime import datetime

# ================= 配置区域 =================
# 1. 监控币种 
# 注意：Kraken 交易所的主流交易对是 USD，不是 USDT
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD']

# 2. 监控周期
TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']

# 3. 倒金字塔阈值配置 (核心优化逻辑)
# 逻辑：小周期噪音大，必须极度严格；大周期趋势稳，可以宽容
THRESHOLD_CONFIG = {
    '5m':  0.004,  # 0.6% (极严)
    '15m': 0.005,  # 0.8%
    '1h':  0.012,  # 1.2%
    '4h':  0.015,  # 1.5%
    '1d':  0.030,  # 3.0%
    '1w':  0.050,  # 5.0%
}

# 4. PushPlus Token (从 GitHub Secrets 读取)
PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN')
# ============================================

def send_wechat(content):
    """发送微信推送"""
    if not PUSHPLUS_TOKEN:
        print("⚠️ 未检测到 PUSHPLUS_TOKEN，跳过推送")
        return

    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "🔥 均线粘合变盘预警",
        "content": content,
        "template": "html"
    }
    try:
        response = requests.post(url, json=data)
        print(f"推送结果: {response.text}")
    except Exception as e:
        print(f"推送失败: {e}")

def fetch_ohlcv(exchange, symbol, timeframe, limit=720):
    """
    获取K线数据
    修改点：默认 limit 从 150 改为 720，确保 EMA120 计算准确
    """
    try:
        # 尝试获取数据
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"获取 {symbol} {timeframe} 失败: {e}")
        return pd.DataFrame()

def analyze_data(df, timeframe):
    """
    分析均线密集度
    """
    if df.empty or len(df) < 120: 
        return None
    
    # 1. 计算均线 (MA 和 EMA)
    periods = [20, 60, 120]
    for p in periods:
        df[f'MA_{p}'] = df['close'].rolling(window=p).mean()
        # adjust=False 模仿同花顺/TradingView 算法
        df[f'EMA_{p}'] = df['close'].ewm(span=p, adjust=False).mean()
    
    row = df.iloc[-1]
    
    # 2. 提取6根均线的数值
    ma_cols = ['MA_20', 'MA_60', 'MA_120', 'EMA_20', 'EMA_60', 'EMA_120']
    values = [row[c] for c in ma_cols if pd.notnull(row[c])]
    
    if len(values) < 6: return None

    max_ma = max(values)
    min_ma = min(values)
    # 计算最大均线和最小均线的价差百分比
    spread_pct = (max_ma - min_ma) / min_ma
    
    # 3. 获取动态阈值
    current_threshold = THRESHOLD_CONFIG.get(timeframe, 0.012)
    
    # 4. 判断位置 (多头/空头)
    if row['close'] > max_ma: 
        position_desc = "<font color='#28a745'><b>★ 看涨 (站上所有均线)</b></font>"
    elif row['close'] < min_ma: 
        position_desc = "<font color='#dc3545'><b>★ 看跌 (跌破所有均线)</b></font>"
    else: 
        position_desc = "<font color='#ffc107'><b>均线纠缠中</b></font>"
    
    return {
        'price': row['close'],
        'spread': spread_pct,
        'is_dense': spread_pct <= current_threshold, # 是否触发信号
        'threshold': current_threshold,
        'position_desc': position_desc
    }

def main():
    # 初始化交易所：使用 Kraken 避免美国IP封锁
    exchange = ccxt.kraken({
        'timeout': 30000, 
        'enableRateLimit': True,
    })

    msg_lines = []
    print("🚀 开始云端扫描 (Kraken 节点)...")

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            # 1. 获取数据 (limit=720)
            df = fetch_ohlcv(exchange, symbol, tf)
            if df.empty: continue
            
            # 2. 分析
            res = analyze_data(df, tf)
            if not res: continue

            # 3. 只有【达标】的数据才放入推送列表
            if res['is_dense']:
                clean_symbol = symbol.replace('/USD', '') # 去掉后缀显示更简洁
                spread_show = f"{res['spread']*100:.2f}%"
                thresh_show = f"{res['threshold']*100:.1f}%"
                
                # 构建单条消息 HTML
                line = (
                    f"<b>{clean_symbol} - {tf}</b><br>"
                    f"当前价格: {res['price']:.2f}<br>"
                    f"密集度: {spread_show} (阈值 ≤{thresh_show})<br>"
                    f"方向: {res['position_desc']}<br>"
                    "------------------------------"
                )
                msg_lines.append(line)
                print(f"✅ 发现信号: {symbol} {tf} | 密集度: {spread_show}") 
            else:
                # 打印日志方便调试，但不推送
                print(f"未触发: {symbol} {tf} | 密集度: {res['spread']*100:.2f}% > {res['threshold']*100:.1f}%")
            
            # 适度延时，防止API超频
            time.sleep(0.5)

    # 4. 汇总发送
    if msg_lines:
        final_html = "<br>".join(msg_lines)
        # 添加底部时间
        final_html += f"<br><br>扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        send_wechat(final_html)
        print("📨 推送已发送")
    else:
        print("😴 本次扫描无符合条件的信号，不打扰。")

if __name__ == "__main__":
    main()
