import re
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.graph_objects as go


# ===============================
# 信用需給（Margin Balance）スクレイピング
# ===============================
def get_margin_balance(ticker: str):
    """
    Yahooファイナンスのトップ（または信用情報欄）から信用買残・売残・倍率を取得する。
    ログイン不要の公開情報のみ使用。
    """
    base_url = f"https://finance.yahoo.co.jp/quote/{ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        r = requests.get(base_url, headers=headers, timeout=5)
        if r.status_code != 200:
            return None
        
        soup = BeautifulSoup(r.content, "html.parser")
        
        # クラス名などは変動リスクがあるため、キーワード探索で粘る
        # "信用買残", "信用売残", "信用倍率" のテキストを持つ要素の近傍を探す手法
        
        data = {
            "buy_rem": "-",    # 信用買残
            "sell_rem": "-",   # 信用売残
            "ratio": "-",      # 信用倍率
            "date": "-"        # 基準日
        }
        
        # 全テキストから探索（少し強引だが構造変化に強い）
        # ただしYahooはSPA化が進んでいるため、SSRされている範囲で取れるか確認
        # セレクタで見つかればラッキー
        
        # 2024/01時点の構造に近い形での探索
        # <span class="_3rXWJKZF">信用買残</span>...<span class="_3rXWJKZF">123,400株</span>
        
        sections = soup.find_all("section")
        margin_section = None
        for s in sections:
            if "信用取引情報" in s.get_text():
                margin_section = s
                break
        
        if margin_section:
            # セクション内のdl/dt/ddなどを解析
            text = margin_section.get_text()
            
            # 正規表現で引っこ抜く（"信用買残1,234,500株" のようなパターン）
            # 数値にはカンマが含まれる
            m_buy = re.search(r"信用買残([\d,]+)株", text)
            m_sell = re.search(r"信用売残([\d,]+)株", text)
            m_ratio = re.search(r"信用倍率([\d,.]+)倍", text)
            m_date = re.search(r"\(([\d/]+)\)", text) # 日付 (01/24) とか

            if m_buy: data["buy_rem"] = m_buy.group(1)
            if m_sell: data["sell_rem"] = m_sell.group(1)
            if m_ratio: data["ratio"] = m_ratio.group(1)
            if m_date: data["date"] = m_date.group(1)
            
        return data

    except Exception as e:
        print(f"Scrape Error: {e}")
        return None

# ===============================
# 価格帯別出来高（Volume Profile）計算
# ===============================
def calc_volume_profile(ticker: str, mode="short"):
    """
    mode="short": 直近5日（1分足ベース）でザラ場・直近の出来高分布を見る
    mode="mid": 直近20日（日足ベース）で中期のしこりを見る
    """
    try:
        if mode == "short":
            # 1分足は7日前までしか取れないので "5d" 指定
            df = yf.download(ticker, period="5d", interval="1m", progress=False)
        else:
            # 日足、約1ヶ月
            df = yf.download(ticker, period="1mo", interval="1d", progress=False)
            
        if df is None or df.empty:
            return None
            
        # MultiIndex解除
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 必要な列: Close（または平均価格）, Volume
        # 価格帯を決める
        price = df["Close"]
        volume = df["Volume"]
        
        min_p = price.min()
        max_p = price.max()
        
        if min_p == max_p:
            return None
            
        # ビン分割（価格の刻みに合わせたいが、簡易的に30分割）
        # ステップ値をそれっぽく丸める処理を入れると綺麗だが、一旦単純分割
        bins = np.linspace(min_p, max_p, 31) # 30区間
        
        # digitizeで所属ビンを判定
        # 1オリジンで返ってくるので -1 する
        indices = np.digitize(price, bins) - 1
        
        # ビンごとのVolume合計
        profile = {}
        for i, vol in zip(indices, volume):
            if 0 <= i < len(bins)-1:
                # ビンの中央値または下限をキーにする
                p_range_val = (bins[i] + bins[i+1]) / 2
                p_key = int(p_range_val) # 整数丸め
                profile[p_key] = profile.get(p_key, 0) + vol
                
        # リスト化してソート（価格降順）
        result = sorted(profile.items(), key=lambda x: x[0], reverse=True)
        return result

    except Exception as e:
        print(f"VP Error: {e}")
        return None


# ===============================
# テキストグラフ生成
# ===============================
# ===============================
# 需給評価ロジック & HTMLテーブル生成
# ===============================
def analyze_volume_zone(vol, max_vol, is_current_price_zone):
    """
    ボリュームと現在価格位置から「定性的な評価」を返す
    """
    ratio = vol / max_vol if max_vol > 0 else 0
    
    labels = []
    
    # ボリューム判定
    if ratio >= 0.8:
        labels.append("★ 巨大なしこり") # 赤系にしたい
    elif ratio >= 0.5:
        labels.append("厚いゾーン")
    elif ratio <= 0.1:
        labels.append("真空地帯（抜けたら速い）")
        
    # 現在値判定
    if is_current_price_zone:
        labels.append("📍 現在の主戦場")
        
    return " / ".join(labels) if labels else ""

def generate_volume_profile_table(profile_data, current_price, title):
    """
    Dashの各種コンポーネント(html.Table等)を返す
    """
    if not profile_data:
        return html.Div(f"{title}: データなし")

    max_vol = max(p[1] for p in profile_data)
    
    # テーブルヘッダー
    header = html.Tr([
        html.Th("価格帯 (円)", style={"padding": "8px", "border": "1px solid #ccc", "backgroundColor": "#f8fafc"}),
        html.Th("出来高 (株)", style={"padding": "8px", "border": "1px solid #ccc", "backgroundColor": "#f8fafc"}),
        html.Th("評価", style={"padding": "8px", "border": "1px solid #ccc", "backgroundColor": "#f8fafc"}),
    ])
    
    rows = []
    limit_count = 0
    total_vol = sum(p[1] for p in profile_data)
    
    # ビン幅推定 (最初の2つの差分から)
    bin_width = 0
    if len(profile_data) > 1:
        bin_width = abs(profile_data[0][0] - profile_data[1][0])
    
    for price, vol in profile_data:
        # 1%未満は省略
        if total_vol > 0 and (vol / total_vol) < 0.01:
            continue
            
        limit_count += 1
        if limit_count > 15: # 長くなりすぎないように
            break
            
        # 範囲表示 (ex: 3400 - 3500)
        p_lower = int(price - bin_width/2)
        p_upper = int(price + bin_width/2)
        price_range_text = f"{p_lower:,} - {p_upper:,}"
        
        # 現在値がこの範囲に含まれるか
        is_current = (p_lower <= current_price < p_upper)
        
        evaluation = analyze_volume_zone(vol, max_vol, is_current)
        
        # 背景色ロジック
        bg_color = "transparent"
        font_weight = "normal"
        color = "#333"
        
        if "巨大なしこり" in evaluation:
            bg_color = "#fee2e2" # 薄い赤
            font_weight = "bold"
        elif "主戦場" in evaluation:
            bg_color = "#fef9c3" # 薄い黄色
            font_weight = "bold"
        elif "真空" in evaluation:
            color = "#94a3b8" # グレー
            
        rows.append(html.Tr([
            html.Td(price_range_text, style={"padding": "6px", "border": "1px solid #eee", "textAlign": "center"}),
            html.Td(f"{vol:,}", style={"padding": "6px", "border": "1px solid #eee", "textAlign": "right"}),
            html.Td(evaluation, style={"padding": "6px", "border": "1px solid #eee", "backgroundColor": bg_color, "color": color, "fontWeight": font_weight}),
        ]))

    return html.Div([
        html.H4(title, style={"fontSize": "16px", "marginBottom": "4px", "marginTop": "16px", "borderLeft": "4px solid #3b82f6", "paddingLeft": "8px"}),
        html.Table(
            [header] + rows,
            style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"}
        )
    ])


# ===============================
# 設定（楽天の日足に合わせて2年）
# ===============================
LOOKBACK_DAYS = 365 * 2


# ===============================
# ティッカー整形（285A対応）
# - 7203 -> 7203.T
# - 285A -> 285A.T
# - 7203.T / 285A.T -> そのまま
# - US銘柄などはそのまま
# ===============================
def normalize_ticker(code: str) -> str:
    code = (code or "").strip().upper()
    if not code:
        return ""
    if code.endswith(".T"):
        return code
    if code.isdigit():
        return f"{code}.T"
    # 285A のような「数字+英字」も東証扱いで .T を付与
    if re.fullmatch(r"\d{3,4}[A-Z]", code):
        return f"{code}.T"
    return code


# ===============================
# 銘柄名の取得（yfinance）
# ===============================
def get_ticker_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        for k in ["longName", "shortName", "name"]:
            v = info.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    except Exception:
        pass
    return ""


# ===============================
# SDI（MFIベース）
# ===============================
def calc_sdi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        raise KeyError(f"Missing columns from price data: {missing}")

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    mf = tp * df["Volume"]

    delta = tp.diff()
    pos = mf.where(delta > 0, 0.0)
    neg = mf.where(delta < 0, 0.0)

    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.abs().rolling(period).sum()

    mfr = pos_sum / neg_sum.replace(0, np.nan)
    sdi = 100 - (100 / (1 + mfr))
    return sdi.clip(0, 100)


# ===============================
# RSI（Cutler / SMA版）※楽天準拠
# ===============================
def calc_rsi_cutler(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.clip(0, 100)


# ===============================
# SDI状態（表示用）
# ===============================
def judge_sdi(v: float) -> str:
    if pd.isna(v):
        return ""
    if v >= 70:
        return "強い買い圧力"
    elif v >= 50:
        return "やや買い優勢"
    elif v >= 30:
        return "やや売り優勢"
    else:
        return "強い売り圧力"


def state_badge(text: str):
    palette = {
        "強い買い圧力": ("#FFD6D6", "#4A1D1D"),
        "やや買い優勢": ("#FFF2CC", "#4A3B10"),
        "やや売り優勢": ("#DFF2E1", "#1F3D2A"),
        "強い売り圧力": ("#D6E8FF", "#1E2D4D"),
    }
    bg, fg = palette.get(text, ("#f1f5f9", "#0f172a"))
    return html.Span(
        text,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "2px 10px",
            "borderRadius": "999px",
            "fontWeight": "700",
            "display": "inline-block",
            "lineHeight": "1.6",
        },
    )


# ===============================
# シグナル（当日だけ点灯）＋ なし/A/B/C 切替
#
# なし: 点灯しない
# A: RSI30回復（前日<30 & 当日>=30）
# B: RSIがSDIを上抜けクロス
# C: A または B（A|B） ←（元DをCに置換）
#
# 共通フィルター（あなたの方針）:
#  - RSI<50 かつ SDI<50 の時だけ点灯（過熱域は点灯しない）
# ===============================
def make_entry_signal(df: pd.DataFrame, sig_mode: str) -> pd.DataFrame:
    out = df.sort_values("Date", ascending=True).copy()

    sdi = pd.to_numeric(out["SDI"], errors="coerce")
    rsi = pd.to_numeric(out["RSI14"], errors="coerce")

    # A: RSI30回復
    A = (rsi.shift(1) < 30) & (rsi >= 30)

    # B: RSIがSDIを上抜けクロス
    B = (rsi.shift(1) <= sdi.shift(1)) & (rsi > sdi)

    # 共通フィルター: 50以上は割安じゃないので点灯しない
    cheap_filter = (rsi < 50) & (sdi < 50)

    sig_mode = (sig_mode or "NONE").upper()

    if sig_mode == "A":
        entry_raw = A & cheap_filter
        mode_text = "シグナル: A（RSI30回復）"
    elif sig_mode == "B":
        entry_raw = B & cheap_filter
        mode_text = "シグナル: B（RSIがSDIを上抜け）"
    elif sig_mode == "C":
        entry_raw = (A | B) & cheap_filter
        mode_text = "シグナル: C（AまたはB）"
    else:
        entry_raw = pd.Series(False, index=out.index)
        mode_text = "シグナル: なし"

    out["Signal"] = np.where(entry_raw.fillna(False), "エントリー(買い)", "")
    out["SignalModeText"] = mode_text
    return out


# ===============================
# 表示整形
# ===============================
COL_JP = {
    "Date": "日付",
    "Open": "始値",
    "High": "高値",
    "Low": "安値",
    "Close": "終値",
    "Volume": "出来高",
    "SDI": "SDI",
    "RSI14": "RSI(14)",
    "状態": "状態",
    "Signal": "シグナル",
}


def fmt_int_comma(x):
    if pd.isna(x):
        return ""
    try:
        return f"{int(round(float(x))):,}"
    except Exception:
        return ""


# ===============================
# Dash App
# ===============================
app = Dash(__name__, meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])
server = app.server  # Gunicorn用にserverを公開
app.title = "株需給判定（2年・楽天RSI・エントリー点灯）"

EMPTY_FIG = go.Figure()
EMPTY_FIG.update_layout(
    yaxis=dict(range=[0, 100]),
    height=420,
    margin=dict(l=25, r=10, t=20, b=40),
    hovermode="x unified",
)

app.layout = html.Div(
    style={"maxWidth": "1200px", "margin": "0 auto", "padding": "0 8px"},
    children=[
        html.H2("需給スイング判定", style={"textAlign": "center", "fontSize": "20px", "marginTop": "10px"}),

        # btnなし：入力したら即反映（debounce=True）
        html.Div(
            style={"display": "flex", "gap": "8px", "alignItems": "center"},
            children=[
                dcc.Input(
                    id="code",
                    value="7203",
                    debounce=True,
                    style={"flex": 1, "height": "36px", "fontSize": "16px"}
                ),
            ],
        ),

        html.Div(
            style={"marginTop": "10px"},
            children=[
                dcc.RadioItems(
                    id="sig_mode",
                    options=[
                        {"label": "なし", "value": "NONE"},
                        {"label": "A", "value": "A"},
                        {"label": "B", "value": "B"},
                        {"label": "C", "value": "C"},
                    ],
                    value="NONE",
                    inline=True,
                    style={"fontSize": "14px", "fontWeight": "bold"},
                    inputStyle={"marginRight": "4px", "marginLeft": "8px"}
                ),
                html.Div(
                    "A: RSI30回復 / B: RSI>SDI / C: AorB",
                    style={"fontSize": "11px", "color": "#475569", "marginTop": "4px"},
                ),
                html.Div(
                    "※RSI<50 & SDI<50 の時のみ点灯",
                    style={"fontSize": "11px", "color": "#475569"},
                ),
            ],
        ),

        html.Div(id="summary", style={"marginTop": "10px"}),
        dcc.Graph(id="graph", figure=EMPTY_FIG, config={'displayModeBar': False}),

        html.H4("過去2年（22営業日 / ページ）", style={"fontSize": "16px", "marginBottom": "8px"}),
        dash_table.DataTable(
            id="table",
            page_size=22,
            style_as_list_view=True,
            style_table={"width": "100%", "overflowX": "auto", "border": "none"},
            style_cell={
                "textAlign": "right",
                "fontSize": "11px",
                "padding": "4px 4px",
                "whiteSpace": "nowrap",
                "height": "28px",
                "lineHeight": "1",
                "border": "none",
                "backgroundColor": "transparent",
            },
            style_header={
                "fontWeight": "600",
                "textAlign": "center",
                "fontSize": "11px",
                "padding": "4px 4px",
                "height": "28px",
                "backgroundColor": "transparent",
                "border": "none",
                "borderBottom": "1px solid #e5e7eb",
            },
            style_data={"border": "none", "borderBottom": "1px solid #f1f5f9"},
            style_cell_conditional=[
                {"if": {"column_id": "日付"}, "textAlign": "center"},
                {"if": {"column_id": "状態"}, "textAlign": "center", "fontWeight": "bold"},
                {"if": {"column_id": "シグナル"}, "textAlign": "center", "fontWeight": "700"},
            ],
            style_data_conditional=[
                {"if": {"filter_query": '{シグナル} = "エントリー(買い)"'}, "backgroundColor": "#FFE8F0"},

                {"if": {"column_id": "状態", "filter_query": '{状態} = "強い買い圧力"'},
                 "backgroundColor": "#FFD6D6", "color": "#4A1D1D", "borderRadius": "8px"},
                {"if": {"column_id": "状態", "filter_query": '{状態} = "やや買い優勢"'},
                 "backgroundColor": "#FFF2CC", "color": "#4A3B10", "borderRadius": "8px"},
                {"if": {"column_id": "状態", "filter_query": '{状態} = "やや売り優勢"'},
                 "backgroundColor": "#DFF2E1", "color": "#1F3D2A", "borderRadius": "8px"},
                {"if": {"column_id": "状態", "filter_query": '{状態} = "強い売り圧力"'},
                 "backgroundColor": "#D6E8FF", "color": "#1E2D4D", "borderRadius": "8px"},
            ],
        ),
    ],
)


@app.callback(
    Output("summary", "children"),
    Output("graph", "figure"),
    Output("table", "data"),
    Output("table", "columns"),
    Input("code", "value"),
    Input("sig_mode", "value"),
)
def update(code, sig_mode):
    summary = ""
    fig = EMPTY_FIG
    data = []
    columns = []

    if not code:
        return summary, fig, data, columns

    ticker = normalize_ticker(code)
    if not ticker:
        return summary, fig, data, columns

    end = datetime.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    try:
        df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    except Exception as e:
        summary = html.Div(["❌ yfinance取得で例外: ", html.Code(str(e))])
        return summary, fig, data, columns

    if df is None or df.empty:
        summary = "❌ データ取得失敗（ティッカー/ネットワーク確認）"
        return summary, fig, data, columns

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 余計な列は落とす
    for drop in ["Adj Close", "Dividends", "Stock Splits"]:
        if drop in df.columns:
            df = df.drop(columns=[drop])

    df = df.reset_index()

    name = get_ticker_name(ticker)

    try:
        df["SDI"] = calc_sdi(df)
        df["RSI14"] = calc_rsi_cutler(df["Close"], period=14).round(2)
    except Exception as e:
        summary = html.Div(["❌ 指標計算で例外: ", html.Code(str(e))])
        return summary, fig, data, columns

    df["状態"] = df["SDI"].apply(judge_sdi)

    df_sig = make_entry_signal(df, sig_mode=sig_mode)
    df_desc = df_sig.sort_values("Date", ascending=False).copy()

    latest_sdi = float(df_desc["SDI"].iloc[0])
    latest_state = df_desc["状態"].iloc[0]
    latest_rsi14 = float(df_desc["RSI14"].iloc[0]) if pd.notna(df_desc["RSI14"].iloc[0]) else np.nan
    sig_text = df_desc["SignalModeText"].iloc[0]
    ticker_text = f"{ticker}（{name}）" if name else ticker

    # 点灯回数 & 直近点灯日（モード切替に連動）
    entry_mask = (df_sig["Signal"] == "エントリー(買い)")
    entry_count = int(entry_mask.sum())
    if entry_count > 0:
        last_entry_dt = pd.to_datetime(df_sig.loc[entry_mask, "Date"], errors="coerce").max()
        last_entry_date = last_entry_dt.strftime("%Y/%m/%d") if pd.notna(last_entry_dt) else "-"
    else:
        last_entry_date = "-"

    # --------------------------
    # 信用需給 & 価格帯別出来高レポート作成
    # --------------------------
    margin_data = get_margin_balance(ticker)
    vp_short = calc_volume_profile(ticker, mode="short")
    vp_mid = calc_volume_profile(ticker, mode="mid")
    
    # 信用情報の整形
    # "信用買残: 123,400 (+1,200) / 倍率: 2.30" みたいな一行
    margin_text = "信用情報取得失敗"
    if margin_data and margin_data["buy_rem"] != "-":
        margin_text = (
            f"信用買残: {margin_data['buy_rem']}株 / "
            f"売残: {margin_data['sell_rem']}株 / "
            f"倍率: {margin_data['ratio']}倍 ({margin_data['date']}時点)"
        )
    
    # VPレポート整形 (Dash Componentへ変更)
    # 現在価格を取得（dfの最新Close）
    current_price = df["Close"].iloc[-1] if not df.empty else 0
    
    table_short = generate_volume_profile_table(vp_short, current_price, f"直近5日 ({int(current_price):,}円周辺・短期)")
    table_mid = generate_volume_profile_table(vp_mid, current_price, f"直近1ヶ月 ({int(current_price):,}円周辺・中期)")
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary_div = html.Div(
        style={"fontSize": "14px", "marginTop": "6px", "fontFamily": "sans-serif"},
        children=[
            html.Div([
                html.Span(f"{sig_text} / "),
                html.Span("RSI方式: Cutler / "),
                html.Span(f"銘柄: {ticker_text} / 最新SDI: {latest_sdi:.2f}（"),
                state_badge(latest_state),
                html.Span(f"） / RSI(14): {latest_rsi14:.2f}"),
            ]),
            html.Div(f"過去2年の点灯回数: {entry_count:,}回 / 直近: {last_entry_date}", style={"marginTop": "2px"}),
            
            # --- レポート表示エリア ---
            html.Details(
                open=True,
                style={"marginTop": "12px", "border": "1px solid #e2e8f0", "borderRadius": "4px", "padding": "8px"},
                children=[
                    html.Summary("📊 需給・価格帯レポート (クリックで開閉)", style={"fontWeight": "bold", "cursor": "pointer", "marginBottom": "8px"}),
                    
                    html.Div(
                        style={"padding": "8px", "backgroundColor": "#fff"},
                        children=[
                            html.Div(f"更新日時: {now_str}", style={"fontSize": "11px", "color": "#64748b", "marginBottom": "8px", "textAlign": "right"}),
                            
                            html.Div(
                                style={"border": "1px solid #ddd", "padding": "8px", "marginBottom": "12px", "backgroundColor": "#f8fafc", "borderRadius": "4px"},
                                children=[html.B(margin_text)]
                            ),
                            
                            html.Div(
                                style={"display": "flex", "flexWrap": "wrap", "gap": "20px"},
                                children=[
                                    html.Div(table_short, style={"flex": "1", "minWidth": "300px"}),
                                    html.Div(table_mid, style={"flex": "1", "minWidth": "300px"}),
                                ]
                            )
                        ]
                    )
                ]
            )
        ],
    )

    # --------------------------
    # グラフ（SDI + RSI14）
    # --------------------------
    df_asc = df_sig.sort_values("Date", ascending=True).copy()
    fig = go.Figure()

    PASTEL_RED = "#FF9AA2"
    PASTEL_BLUE = "#A0C4FF"

    fig.add_trace(go.Scatter(
        x=df_asc["Date"], y=df_asc["SDI"],
        mode="lines", name="SDI",
        line=dict(color=PASTEL_RED, width=2),
        hovertemplate="日付=%{x|%Y/%m/%d}<br>SDI=%{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_asc["Date"], y=df_asc["RSI14"],
        mode="lines", name="RSI(14)",
        line=dict(color=PASTEL_BLUE, width=2),
        hovertemplate="日付=%{x|%Y/%m/%d}<br>RSI(14)=%{y:.2f}<extra></extra>",
    ))

    # 点灯日のマーカー（当日だけ）
    marks = df_asc[df_asc["Signal"] == "エントリー(買い)"].copy()
    if not marks.empty:
        fig.add_trace(go.Scatter(
            x=marks["Date"],
            y=marks["RSI14"],
            mode="markers",
            name="エントリー(買い)",
            marker=dict(size=10, symbol="circle"),
            hovertemplate="日付=%{x|%Y/%m/%d}<br>エントリー(買い)<br>RSI(14)=%{y:.2f}<extra></extra>",
        ))

    fig.update_yaxes(range=[0, 100])
    fig.add_hline(y=75, line_width=1, line_dash="dot")
    fig.add_hline(y=50, line_width=1, line_dash="dot")
    fig.add_hline(y=25, line_width=1, line_dash="dot")

    fig.update_layout(
        height=460,
        margin=dict(l=40, r=20, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        template="plotly_white", # 少し綺麗に
    )
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot")

    # --------------------------
    # テーブル整形
    # --------------------------
    view = df_desc.copy()
    view["Date"] = pd.to_datetime(view["Date"], errors="coerce").dt.strftime("%Y/%m/%d")
    view["SDI"] = pd.to_numeric(view["SDI"], errors="coerce").round(2)
    view["RSI14"] = pd.to_numeric(view["RSI14"], errors="coerce").round(2)

    for col in ["Open", "High", "Low", "Close"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").apply(fmt_int_comma)
    if "Volume" in view.columns:
        view["Volume"] = pd.to_numeric(view["Volume"], errors="coerce").apply(fmt_int_comma)

    # 内部列は表示しない
    for drop_col in ["SignalModeText"]:
        if drop_col in view.columns:
            view = view.drop(columns=[drop_col])

    view = view.rename(columns=COL_JP)

    columns = [{"name": c, "id": c} for c in view.columns]
    data = view.to_dict("records")

    return summary_div, fig, data, columns


if __name__ == "__main__":
    app.run(debug=True, port=8052, host="0.0.0.0", use_reloader=False)
