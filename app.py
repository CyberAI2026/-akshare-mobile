import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title='A股行情抓取与校验', page_icon='📈', layout='wide')
st.title('A股行情抓取与数据质量校验')
st.caption('手机端操作 · 云端运行 · 支持25日 / 120日 / 250日')

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


def parse_input(text: str):
    rows=[]
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue
        parts=line.replace(',', ' ').replace('，',' ').split()
        code=''.join(ch for ch in parts[0] if ch.isdigit())
        if len(code) != 6:
            continue
        name=' '.join(parts[1:]).strip() if len(parts)>1 else ''
        rows.append((code,name))
    # preserve order, dedupe by code
    seen=set(); out=[]
    for r in rows:
        if r[0] not in seen:
            out.append(r); seen.add(r[0])
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def get_name_map():
    df = ak.stock_info_a_code_name()
    df['code'] = df['code'].astype(str).str.zfill(6)
    return dict(zip(df['code'], df['name']))


def fetch_stock(code, days):
    # Pull enough calendar days to cover requested trading days + warmup.
    end = datetime.now().strftime('%Y%m%d')
    start = '20240101' if days >= 250 else ('20250101' if days >= 120 else '20260101')
    df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date=start, end_date=end, adjust='qfq')
    if df is None or df.empty:
        return pd.DataFrame()
    rename = {
        '日期':'日期','开盘':'开盘价','收盘':'收盘价','最高':'最高价','最低':'最低价',
        '成交量':'成交量','成交额':'成交额','换手率':'换手率'
    }
    cols=[c for c in rename if c in df.columns]
    df=df[cols].rename(columns=rename).copy()
    df['日期']=pd.to_datetime(df['日期'])
    df=df.sort_values('日期').tail(days).reset_index(drop=True)
    return df


def validate_ohlc(df):
    if df.empty:
        return 0
    bad = (
        (df['最高价'] < df[['开盘价','收盘价','最低价']].max(axis=1)) |
        (df['最低价'] > df[['开盘价','收盘价','最高价']].min(axis=1))
    )
    return int(bad.sum())


def add_vol5(df):
    x=df.copy()
    prev5 = x['成交量'].shift(1).rolling(5).mean()
    x['5日成交量比'] = x['成交量'] / prev5
    return x


def fetch_indices(days=120):
    specs=[
        ('sh000001','上证指数'),('sz399001','深证成指'),('sz399006','创业板指'),
        ('sh000688','科创50'),('bj899050','北证50')
    ]
    out=[]
    for code,name in specs:
        try:
            # AKShare index interface expects pure symbol for common mainland indices.
            pure = ''.join(ch for ch in code if ch.isdigit())
            df=ak.index_zh_a_hist(symbol=pure, period='daily', start_date='20250101', end_date=datetime.now().strftime('%Y%m%d'))
            if df is None or df.empty:
                continue
            ren={'日期':'日期','开盘':'开盘价','收盘':'收盘价','最高':'最高价','最低':'最低价','成交量':'成交量','成交额':'成交额'}
            df=df[[c for c in ren if c in df.columns]].rename(columns=ren)
            df['日期']=pd.to_datetime(df['日期'])
            df=df.sort_values('日期').tail(days)
            df.insert(0,'指数名称',name); df.insert(0,'指数代码',code)
            out.append(df)
        except Exception:
            continue
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def to_excel(sheets: dict):
    bio=BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        for name,df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return bio.getvalue()

if st.button('开始抓取并生成Excel', type='primary', use_container_width=True):
    rows=parse_input(code_text)
    if not rows:
        st.error('没有解析到有效的6位股票代码。')
        st.stop()
    days=MODE_CONFIG[mode]
    try:
        name_map=get_name_map()
    except Exception as e:
        st.error(f'无法获取A股代码名称表：{e}')
        st.stop()

    data_parts=[]; qa=[]; static=[]
    progress=st.progress(0)
    status=st.empty()

    for i,(code,input_name) in enumerate(rows, start=1):
        actual_name=name_map.get(code,'')
        consistent=(not input_name) or (actual_name == input_name)
        err=''
        df=pd.DataFrame()
        try:
            if not actual_name:
                err='代码未在A股代码名称表中找到'
            elif not consistent:
                err=f'输入名称“{input_name}”与代码实际名称“{actual_name}”不一致'
            else:
                df=fetch_stock(code, days if days != 120 else 125)
                if days == 120 and not df.empty:
                    df=add_vol5(df).tail(120).reset_index(drop=True)
                elif not df.empty:
                    df=df.tail(days).reset_index(drop=True)
                if df.empty:
                    err='未抓取到日线数据'
                else:
                    df.insert(0,'股票名称',actual_name); df.insert(0,'股票代码',code)
                    data_parts.append(df)
                    static.append({'股票代码':code,'股票名称':actual_name})
        except Exception as e:
            err=str(e)

        if not df.empty:
            first=df['日期'].min().date().isoformat(); last=df['日期'].max().date().isoformat()
            n=len(df); dup=int(df.duplicated(['股票代码','日期']).sum())
            ohlc=validate_ohlc(df)
            zero_vol=int((pd.to_numeric(df.get('成交量'), errors='coerce').fillna(0)<=0).sum()) if '成交量' in df else None
            zero_amt=int((pd.to_numeric(df.get('成交额'), errors='coerce').fillna(0)<=0).sum()) if '成交额' in df else None
        else:
            first=last=''; n=0; dup=0; ohlc=0; zero_vol=zero_amt=None
        qa.append({
            '输入股票代码':code,'输入股票名称':input_name,'实际抓取股票代码':code if actual_name else '',
            '实际抓取股票名称':actual_name,'代码名称是否一致':'是' if consistent and actual_name else '否',
            '实际交易日数量':n,'最早日期':first,'最新日期':last,
            '是否包含市场最新交易日':'需结合停牌情况人工复核',
            '成交量单位':'手（AKShare stock_zh_a_hist 常见口径，请以当前接口文档为准）',
            '成交额来源':'行情源真实字段' if n else '',
            '换手率来源':'行情源历史字段' if n else '',
            '重复代码+日期数量':dup,'OHLC逻辑异常数量':ohlc,
            '成交量<=0数量':zero_vol,'成交额<=0数量':zero_amt,
            '异常说明':err,
        })
        progress.progress(i/len(rows)); status.text(f'正在处理 {i}/{len(rows)}：{code} {actual_name or input_name}')

    data=pd.concat(data_parts, ignore_index=True) if data_parts else pd.DataFrame()
    qa_df=pd.DataFrame(qa)
    sheets={}
    if days==25:
        sheets['个股25日日线数据']=data
    elif days==120:
        sheets['个股日线动态数据']=data
        sheets['个股静态属性数据']=pd.DataFrame(static).drop_duplicates('股票代码')
        if include_indices:
            sheets['指数日线数据']=fetch_indices(120)
    else:
        sheets['个股250日日线数据']=data
    sheets['数据质量校验表']=qa_df

    ok=(qa_df['代码名称是否一致']=='是') & (qa_df['实际交易日数量']>0)
    st.success(f'完成：输入 {len(rows)} 只，成功 {int(ok.sum())} 只，异常 {int((~ok).sum())} 只。')
    st.dataframe(qa_df, use_container_width=True, hide_index=True)
    excel=to_excel(sheets)
    fname=f'A股行情_{days}日_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    st.download_button('下载Excel结果', data=excel, file_name=fname, mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

st.divider()
st.markdown('''**说明**\n\n- 这是第一版“数据抓取 + 质量校验”工具，先解决稳定抓数问题。\n- 120日模式已按“当日成交量 ÷ 此前5日平均成交量”计算5日成交量比。\n- 代码为唯一主键；如输入名称与代码真实名称不一致，会直接标记异常并停止该股票正式输出。\n- 后续可以继续加入自动一级粗筛、二级结构评分、三级生命周期分类以及14:50尾盘确认。''')
