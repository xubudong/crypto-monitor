import ccxt
import pandas as pd
import requests  # 新增：用于发送网络请求
import os
from datetime import datetime

# ================= 配置区域 =================
# 注意：Token 不要直接写在代码里，后面教你在 GitHub 设置里填
PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN') 

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
TIMEFRAMES = ['5m','15m', '1h', '4h', '1d'] # 建议云端运行不要太频繁，15分钟起
DENSITY_THRESHOLD = 0.012 
# ===========================================

def send_wechat(title, content):
    """发送微信通知"""
    if not PUSHPLUS_TOKEN:
        print("未设置 Token，跳过发送")
        return
    
    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html"
    }
    try:
        requests.post(url, json=data)
        print("微信推送成功！")
    except Exception as e:
        print(f"推送失败: {e}")

def fetch_and_analyze():
    exchange = ccxt.binance()
    msg_list = []
    
    print("开始扫描...")
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=130)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # 计算均线
                periods = [20, 60, 120]
                values = []
                for p in periods:
                    ma = df['c'].rolling(p).mean().iloc[-1]
                    ema = df['c'].ewm(span=p, adjust=False).mean().iloc[-1]
                    values.extend([ma, ema])
                
                # 核心计算
                max_ma = max(values)
                min_ma = min(values)
                spread = (max_ma - min_ma) / min_ma
                close = df['c'].iloc[-1]
                
                # 判断是否密集
                if spread <= DENSITY_THRESHOLD:
                    # 判断方向
                    if close > max_ma: pos = "🟢 均线上方(看涨)"
                    elif close < min_ma: pos = "🔴 均线下方(看跌)"
                    else: pos = "🟡 均线纠缠中"
                    
                    # 只有真的密集才记录
                    msg = f"<b>{symbol} ({tf})</b><br>当前价格: {close}<br>密集度: {spread*100:.2f}%<br>状态: {pos}<br>------------------"
                    msg_list.append(msg)
                    
            except Exception as e:
                print(f"Error: {e}")
                continue

    # 如果有信号，汇总发送
    if msg_list:
        final_content = "<br>".join(msg_list)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        send_wechat(f"【信号】加密货币均线密集 {current_time}", final_content)
    else:
        print("无信号，不打扰。")

if __name__ == "__main__":
    fetch_and_analyze()
