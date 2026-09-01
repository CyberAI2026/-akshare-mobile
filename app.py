import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta
from io import BytesIO
import time
import random
import re

st.set_page_config(page_title='A股行情抓取与校验 V2', page_icon='📈', layout='wide')
st.title('A股行情抓取与数据质量校验 V2')
st.caption('手机端操作 · 云端运行 · 多数据源回退 · 自动重试 · 代码优先')

MODE_CONFIG = {
    '25日粗筛': 25,
    '120日结构筛选': 120,
    '250日生命周期筛选': 250,
}

DEFAULT_CODES = '''002365 永安药业
002724 海洋王
600801 华新水泥
603188 亚邦股份
600712 南宁百货
002702 海欣食品
000723 美锦能源
000428 华天酒店
000523 红棉股份
002582 好想你
000735 罗牛山
600857 宁波中百
603217 元利科技
601579 会稽山
002322 理工能科
605388 均瑶健康
002882 金龙羽
603716 塞力医疗
603912 佳力图
002973 侨银股份
600536 中国软件
600698 湖南天雁
603797 联泰环保
601002 晋亿实业
600368 五洲交通
300515 三德科技
601609 金田股份
300805 电声股份
603122 合富中国
600833 第一医药'''

mode = st.selectbox('抓取层级', list(MODE_CONFIG))
code_text = st.text_area('股票代码列表（每行一个代码，可附股票名称）', value=DEFAULT_CODES, height=360)
include_indices = st.checkbox('120日模式同时抓取主要指数', value=True)

with st.expander('V2 稳定性设置（一般无需修改）'):
    retry_count = st.slider('单数据源最大重试次数', 1, 4, 2)
    min_pause = st.slider('每次请求最短等待（秒）', 0.2, 2.0, 0.6, 0.1)
    max_pause = st.slider('每次请求最长等待（秒）', 0.5, 4.0, 1.4, 0.1)


def parse_input(text: str):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.replace(',', ' ').replace('，', ' ').split()
        code = ''.join(ch for ch in parts[0] if ch.isdigit())
        if len(code) != 6:
            continue
        name = ' '.join(parts[1:]).strip() if len(parts) > 1 else ''
        rows.append((code, name))
    seen, out = set(), []
    for row in rows:
        if row[0] not in seen:
            out.append(row)
            seen.add(row[0])
    return out


def normalize_name(name: str) -> str:
    if not name:
        return ''
    # 名称仅用于提示，不作为行情抓取阻断条件
    return re.sub(r'\s+', '', str(name)).replace('*', '').replace('ＳＴ', 'ST').upper()


@st.cache_data(ttl=3600, show_spinner=False)
def get_name_map():
    try:
        df = ak.stock_info_a_code_name()
        df['code'] = df['code'].astype(str).str.zfill(6)
        return dict(zip(df['code'], df['name']))
    except Exception:
        return {}


def market_prefix(code: str) -> str:
    if code.startswith(('5', '6', '9')):
        return 'sh' + code
    if code.startswith(('0', '1', '2', '3')):
        return 'sz' + code
    if code.startswith(('4', '8')):
        return 'bj' + code
    return code


def calc_date_range(days: int):
    # 用较长自然日窗口覆盖停牌、节假日，并给120日模式预留5日预热
    need = days + (5 if days == 120 else 0)
    end_dt = datetime.now()
    calendar_days = max(120, int(need * 2.2) + 60)
    start_dt = end_dt - timedelta(days=calendar_days)
    return start_dt.strftime('%Y%m%d'), end_dt.strftime('%Y%m%d')


def standardize_eastmoney(df: pd.DataFrame) -> pd.DataFrame:
    ren = {
        '日期': '日期', '开盘': '开盘价', '最高': '最高价', '最低': '最低价', '收盘': '收盘价',
        '成交量': '成交量', '成交额': '成交额', '换手率': '换手率'
    }
    keep = [c for c in ren if c in df.columns]
    out = df[keep].rename(columns=ren).copy()
    if '日期' in out:
        out['日期'] = pd.to_datetime(out['日期'])
    return out


def standardize_sina(df: pd.DataFrame) -> pd.DataFrame:
    ren = {
        'date': '日期', 'open': '开盘价', 'high': '最高价', 'low': '最低价', 'close': '收盘价',
        'volume': '成交量', 'amount': '成交额', 'turnover': '换手率'
    }
    keep = [c for c in ren if c in df.columns]
    out = df[keep].rename(columns=ren).copy()
    if '日期' in out:
        out['日期'] = pd.to_datetime(out['日期'])
    if '换手率' not in out.columns:
        out['换手率'] = np.nan
    return out


def fetch_em(code: str, start: str, end: str) -> pd.DataFrame:
    df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date=start, end_date=end, adjust='qfq')
    if df is None or df.empty:
        return pd.DataFrame()
    return standardize_eastmoney(df)


def fetch_sina(code: str, start: str, end: str) -> pd.DataFrame:
    symbol = market_prefix(code)
    # 新浪接口使用 YYYYMMDD；若当前 AKShare 版本不支持 qfq，会自动被异常捕获并回退
    df = ak.stock_zh_a_daily(symbol=symbol, start_date=start, end_date=end, adjust='qfq')
    if df is None or df.empty:
        return pd.DataFrame()
    return standardize_sina(df)


def fetch_with_fallback(code: str, days: int, retries: int, pmin: float, pmax: float):
    start, end = calc_date_range(days)
    sources = [
        ('东方财富_stock_zh_a_hist', fetch_em),
        ('新浪_stock_zh_a_daily', fetch_sina),
    ]
    errors = []
    need = days + (5 if days == 120 else 0)

    for source_name, fn in sources:
        for attempt in range(1, retries + 1):
            try:
                time.sleep(random.uniform(pmin, pmax))
                df = fn(code, start, end)
                if df is None or df.empty:
                    raise RuntimeError('接口返回空数据')
                df = df.sort_values('日期').drop_duplicates('日期', keep='last').reset_index(drop=True)
                if len(df) < min(10, need):
                    raise RuntimeError(f'返回交易日过少：{len(df)}')
                return df.tail(need).reset_index(drop=True), source_name, errors
            except Exception as e:
                errors.append(f'{source_name} 第{attempt}次: {type(e).__name__}: {e}')
                time.sleep(random.uniform(pmin, pmax))
    return pd.DataFrame(), '', errors


def validate_ohlc(df):
    needed = {'开盘价', '最高价', '最低价', '收盘价'}
    if df.empty or not needed.issubset(df.columns):
        return 0
    high_ref = df[['开盘价', '收盘价', '最低价']].max(axis=1)
    low_ref = df[['开盘价', '收盘价', '最高价']].min(axis=1)
    return int(((df['最高价'] < high_ref) | (df['最低价'] > low_ref)).sum())


def add_vol5(df):
    x = df.copy()
    prev5 = pd.to_numeric(x['成交量'], errors='coerce').shift(1).rolling(5).mean()
    x['5日成交量比'] = pd.to_numeric(x['成交量'], errors='coerce') / prev5
    return x


def fetch_indices(days=120):
    specs = [
        ('sh000001', '上证指数', '000001'),
        ('sz399001', '深证成指', '399001'),
        ('sz399006', '创业板指', '399006'),
        ('sh000688', '科创50', '000688'),
        ('bj899050', '北证50', '899050'),
    ]
    out = []
    start, end = calc_date_range(days)
    for code, name, pure in specs:
        try:
            time.sleep(random.uniform(min_pause, max_pause))
            df = ak.index_zh_a_hist(symbol=pure, period='daily', start_date=start, end_date=end)
            if df is None or df.empty:
                continue
            ren = {'日期':'日期','开盘':'开盘价','最高':'最高价','最低':'最低价','收盘':'收盘价','成交量':'成交量','成交额':'成交额'}
            df = df[[c for c in ren if c in df.columns]].rename(columns=ren).copy()
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期').tail(days)
            df.insert(0, '指数名称', name)
            df.insert(0, '指数代码', code)
            out.append(df)
        except Exception:
            continue
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def get_static_info(code: str, name: str):
    # V2 先保证日线抓取稳定；静态属性尽力获取，失败不阻断主流程
    return {'股票代码': code, '股票名称': name, '所属行业': '', '最新流通市值': np.nan}


def to_excel(sheets: dict):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return bio.getvalue()


if st.button('开始抓取并生成Excel', type='primary', use_container_width=True):
    rows = parse_input(code_text)
    if not rows:
        st.error('没有解析到有效的6位股票代码。')
        st.stop()

    days = MODE_CONFIG[mode]
    name_map = get_name_map()

    data_parts, qa, static = [], [], []
    progress = st.progress(0)
    status = st.empty()

    for i, (code, input_name) in enumerate(rows, start=1):
        actual_name = name_map.get(code, '')
        display_name = actual_name or input_name
        name_match = (
            '未知' if not actual_name or not input_name
            else ('是' if normalize_name(actual_name) == normalize_name(input_name) else '否（仅提示，不阻断）')
        )

        df, source, errors = fetch_with_fallback(code, days, retry_count, min_pause, max_pause)
        err = ''
        if df.empty:
            err = ' | '.join(errors[-4:]) if errors else '未抓取到日线数据'
        else:
            if days == 120:
                df = add_vol5(df).tail(120).reset_index(drop=True)
            else:
                df = df.tail(days).reset_index(drop=True)
            df.insert(0, '股票名称', display_name)
            df.insert(0, '股票代码', code)
            data_parts.append(df)
            static.append(get_static_info(code, display_name))

        if not df.empty:
            first = df['日期'].min().date().isoformat()
            last = df['日期'].max().date().isoformat()
            n = len(df)
            dup = int(df.duplicated(['股票代码', '日期']).sum())
            ohlc = validate_ohlc(df)
            zero_vol = int((pd.to_numeric(df['成交量'], errors='coerce').fillna(0) <= 0).sum()) if '成交量' in df else None
            zero_amt = int((pd.to_numeric(df['成交额'], errors='coerce').fillna(0) <= 0).sum()) if '成交额' in df else None
            turnover_source = '行情源历史字段' if ('换手率' in df and df['换手率'].notna().any()) else '缺失'
            amount_source = '行情源真实字段' if ('成交额' in df and df['成交额'].notna().any()) else '缺失'
        else:
            first = last = ''
            n = dup = ohlc = 0
            zero_vol = zero_amt = None
            turnover_source = amount_source = ''

        qa.append({
            '输入股票代码': code,
            '输入股票名称': input_name,
            '实际抓取股票代码': code if n else '',
            '实际抓取股票名称': actual_name or input_name,
            '代码是否有效': '是' if (actual_name or n) else '待核验',
            '名称是否一致': name_match,
            '实际交易日数量': n,
            '最早日期': first,
            '最新日期': last,
            '是否包含市场最新交易日': '需结合停牌情况复核' if n else '',
            '实际使用数据源': source,
            '成交量单位': '以当前AKShare接口原始口径为准；使用前请抽样核验',
            '成交额来源': amount_source,
            '换手率来源': turnover_source,
            '重复代码+日期数量': dup,
            'OHLC逻辑异常数量': ohlc,
            '成交量<=0数量': zero_vol,
            '成交额<=0数量': zero_amt,
            '名称差异说明': (f'输入“{input_name}”，行情代码表名称“{actual_name}”' if input_name and actual_name and normalize_name(input_name) != normalize_name(actual_name) else ''),
            '异常说明': err,
        })

        progress.progress(i / len(rows))
        status.text(f'正在处理 {i}/{len(rows)}：{code} {display_name}')

    data = pd.concat(data_parts, ignore_index=True) if data_parts else pd.DataFrame()
    qa_df = pd.DataFrame(qa)
    sheets = {}

    if days == 25:
        sheets['个股25日日线数据'] = data
    elif days == 120:
        sheets['个股日线动态数据'] = data
        sheets['个股静态属性数据'] = pd.DataFrame(static).drop_duplicates('股票代码') if static else pd.DataFrame(columns=['股票代码','股票名称','所属行业','最新流通市值'])
        if include_indices:
            sheets['指数日线数据'] = fetch_indices(120)
    else:
        sheets['个股250日日线数据'] = data

    sheets['数据质量校验表'] = qa_df

    ok = qa_df['实际交易日数量'] > 0
    st.success(f'完成：输入 {len(rows)} 只，成功 {int(ok.sum())} 只，异常 {int((~ok).sum())} 只。')
    if (~ok).any():
        st.warning('仍有失败股票。请重点查看“实际使用数据源”和“异常说明”；V2 不会因股票名称变化而阻断代码行情抓取。')
    st.dataframe(qa_df, use_container_width=True, hide_index=True)

    excel = to_excel(sheets)
    fname = f'A股行情_{days}日_V2_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    st.download_button(
        '下载Excel结果', data=excel, file_name=fname,
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        use_container_width=True
    )

st.divider()
st.markdown('''**V2 说明**

- 股票代码始终是唯一行情查询主键；名称只做提示性校验，名称变更或空格差异不会阻断抓取。
- 历史行情默认先尝试东方财富接口；连接失败时自动重试，再回退到新浪日线接口。
- 每次请求之间加入随机等待，降低云端批量请求触发上游风控的概率。
- 质量校验表会记录每只股票最终使用的数据源和失败原因。
- 若备用数据源没有历史换手率，换手率保留为空，不用最新流通股本伪造历史换手率。
- V2 先解决云端稳定抓数。120日静态行业/流通市值字段暂不作为阻断项，后续在抓数稳定后再补强。''')
