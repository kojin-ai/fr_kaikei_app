"""サークル会計アナライザー (Streamlit)
起動: streamlit run app.py
"""
import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="サークル会計アナライザー", layout="wide")
WEEK = list("月火水木金土日")


def yen(v: float) -> str:
    return f"{'−' if v < 0 else ''}¥{abs(v):,.0f}"


# ---------- 読み込み ----------
def read_file(up) -> dict:
    data = up.getvalue()
    if up.name.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "cp932"):
            try:
                return {"CSV": pd.read_csv(io.BytesIO(data), encoding=enc)}
            except UnicodeDecodeError:
                continue
        raise ValueError("文字コードを判別できませんでした")
    return pd.read_excel(io.BytesIO(data), sheet_name=None)


def sample_data() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for m in range(12):
        y, mo = 2025 + (m + 3) // 12, (m + 3) % 12 + 1
        d = lambda day: pd.Timestamp(y, mo, int(day))
        if mo in (4, 10):
            rows.append((d(8), "部費", 150000, 0, "会計", "前期/後期"))
        if mo == 6:
            rows.append((d(15), "大学補助金", 80000, 0, "会計", ""))
        rows.append((d(rng.integers(3, 10)), "備品", 0, rng.integers(2000, 9000), "田中", ""))
        for _ in range(2):
            rows.append((d(rng.integers(11, 28)), "会場費", 0, rng.integers(5000, 15000), "佐藤", ""))
        rows.append((d(rng.integers(5, 25)), "飲み会", 0, 68000 if mo == 12 else rng.integers(8000, 22000), "鈴木", ""))
        rows.append((d(rng.integers(5, 25)), "交通費", 0, rng.integers(1500, 6000), "高橋", ""))
        if mo == 8:
            rows += [(d(10), "合宿参加費", 150000, 0, "会計", ""), (d(12), "合宿費", 0, 170000, "田中", "宿泊")]
        if mo == 11:
            rows += [(d(3), "学祭売上", 120000, 0, "鈴木", ""), (d(1), "学祭出店費", 0, 80000, "鈴木", "")]
    return pd.DataFrame(rows, columns=["日付", "項目", "収入", "支出", "担当", "メモ"])


def guess(cols, pat, exclude=()):
    return next((c for c in cols if c not in exclude and re.search(pat, c, re.I)), None)


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[,¥￥円\s]", "", regex=True), errors="coerce").fillna(0)


def normalize(df, c_date, c_cat, c_inc, c_exp) -> pd.DataFrame:
    out = pd.DataFrame({"日付": pd.to_datetime(df[c_date], errors="coerce")})
    out["項目"] = df[c_cat].astype(str).str.strip() if c_cat else "(全体)"
    inc = to_num(df[c_inc])
    if c_exp:
        exp = to_num(df[c_exp])
    else:  # 金額1列: マイナスを支出とみなす
        exp, inc = (-inc).clip(lower=0), inc.clip(lower=0)
    out["収入"], out["支出"] = inc, exp
    used = {c_date, c_cat, c_inc, c_exp}
    for c in df.columns:
        if c not in used and c not in out.columns:
            out[c] = df[c].fillna("").astype(str)
    out = out.dropna(subset=["日付"]).sort_values("日付").reset_index(drop=True)
    out["月"] = out["日付"].dt.strftime("%Y-%m")
    out["年度"] = np.where(out["日付"].dt.month >= 4, out["日付"].dt.year, out["日付"].dt.year - 1).astype(str) + "年度"
    out["曜日"] = out["日付"].dt.dayofweek.map(lambda i: WEEK[i]) + "曜"
    return out


def monthly(d: pd.DataFrame) -> pd.DataFrame:
    full = pd.period_range(d["月"].min(), d["月"].max(), freq="M").strftime("%Y-%m")
    return d.groupby("月")[["収入", "支出"]].sum().reindex(full, fill_value=0)


# ---------- サイドバー ----------
with st.sidebar:
    st.header("データ取り込み")
    up = st.file_uploader("Excel / CSV(1行目が見出し)", type=["xlsx", "xls", "csv"])
    if st.button("サンプルデータで試す"):
        st.session_state["sample"] = True
    if up:
        st.session_state["sample"] = False

if up:
    sheets = read_file(up)
    with st.sidebar:
        sname = st.selectbox("シート", list(sheets))
    raw = sheets[sname]
elif st.session_state.get("sample"):
    raw = sample_data()
else:
    st.title("サークル会計アナライザー")
    st.info("左のサイドバーから会計データ(Excel / CSV)をアップロードするか、サンプルデータを試してください。")
    st.stop()

raw = raw.dropna(how="all")
raw.columns = [str(c).strip() for c in raw.columns]
cols = list(raw.columns)
NONE = "(なし)"
g_date = guess(cols, r"日付|日|date")
g_cat = guess(cols, r"項目|科目|費目|内容|category", [g_date])
g_inc = guess(cols, r"収入|入金|income")
g_exp = guess(cols, r"支出|出金|expense")
if not g_inc and not g_exp:
    g_inc = guess(cols, r"金額|amount")

with st.sidebar:
    st.subheader("列の対応づけ")
    c_date = st.selectbox("日付", cols, index=cols.index(g_date) if g_date else 0)
    c_cat = st.selectbox("項目", [NONE] + cols, index=cols.index(g_cat) + 1 if g_cat else 0)
    c_inc = st.selectbox("収入(または金額)", cols, index=cols.index(g_inc) if g_inc else 0)
    c_exp = st.selectbox("支出", [NONE] + cols, index=cols.index(g_exp) + 1 if g_exp else 0)
    st.caption("支出を(なし)にすると、収入列のマイナス値を支出として扱います。")

D = normalize(raw, c_date, None if c_cat == NONE else c_cat, c_inc, None if c_exp == NONE else c_exp)
if D.empty:
    st.error("日付を読み取れる行がありません。列の対応づけを確認してください。")
    st.stop()

M = monthly(D)
extras = [c for c in D.columns if c not in ("日付", "収入", "支出", "月", "年度", "曜日", "項目")]
DIMS = ["月", "年度", "曜日", "項目"] + extras

st.title("サークル会計アナライザー")
t1, t2, t3, t4 = st.tabs(["概要", "自由分析", "高度分析", "データ"])

# ---------- 概要 ----------
with t1:
    inc, exp = D["収入"].sum(), D["支出"].sum()
    k = st.columns(5)
    k[0].metric("総収入", yen(inc))
    k[1].metric("総支出", yen(exp))
    k[2].metric("現在の残高", yen(inc - exp))
    k[3].metric("月平均の支出", yen(exp / len(M)))
    k[4].metric("取引件数", f"{len(D)}件")
    a, b = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=M.index, y=M["収入"], name="収入", marker_color="#0e8f7e")
    fig.add_bar(x=M.index, y=M["支出"], name="支出", marker_color="#d9480f")
    fig.add_scatter(x=M.index, y=(M["収入"] - M["支出"]).cumsum(), name="累計残高", line_color="#2f4bd8")
    fig.update_layout(title="月別の収支と累計残高", barmode="group", legend_orientation="h")
    a.plotly_chart(fig)
    cat = D[D["支出"] > 0].groupby("項目")["支出"].sum().sort_values(ascending=False)
    b.plotly_chart(px.pie(cat.reset_index(), names="項目", values="支出", hole=0.45, title="支出の内訳(項目別)"))

# ---------- 自由分析 ----------
with t2:
    c = st.columns(6)
    d1 = c[0].selectbox("分ける軸", DIMS, index=DIMS.index("項目"))
    d2 = c[1].selectbox("さらに分ける軸", [NONE] + DIMS)
    mname = c[2].selectbox("集計する値", ["支出の合計", "収入の合計", "収支", "件数", "支出の1件平均"])
    ctype = c[3].selectbox("グラフ", ["棒", "積み上げ棒", "横棒", "折れ線", "円", "ドーナツ", "ヒートマップ"])
    order = c[4].selectbox("並び順", ["軸の順", "値が大きい順"])
    topn = c[5].number_input("上位N件(0=全て)", min_value=0, value=0)

    keys = [d1] + ([d2] if d2 != NONE else [])
    gdf = D.groupby(keys).agg(収入=("収入", "sum"), 支出=("支出", "sum"), 件数=("日付", "size")).reset_index()
    gdf["収支"] = gdf["収入"] - gdf["支出"]
    gdf["支出の1件平均"] = gdf["支出"] / gdf["件数"]
    vcol = {"支出の合計": "支出", "収入の合計": "収入"}.get(mname, mname)
    if d2 == NONE:
        gdf["系列"] = vcol
    scol = d2 if d2 != NONE else "系列"
    pv = gdf.pivot_table(index=d1, columns=scol, values=vcol, aggfunc="sum", fill_value=0)
    pv["合計"] = pv.sum(axis=1)
    if order == "値が大きい順":
        pv = pv.sort_values("合計", ascending=False)
    elif d1 == "曜日":
        pv = pv.reindex([w + "曜" for w in WEEK if w + "曜" in pv.index])
    if topn:
        pv = pv.head(int(topn))
    body = pv.drop(columns="合計") if d2 != NONE else pv[["合計"]].rename(columns={"合計": vcol})

    left, right = st.columns([3, 2])
    long = body.reset_index().melt(id_vars=d1, var_name="系列", value_name=vcol)
    if ctype in ("円", "ドーナツ"):
        fig = px.pie(pv.reset_index(), names=d1, values="合計", hole=0.45 if ctype == "ドーナツ" else 0)
    elif ctype == "ヒートマップ" and d2 != NONE:
        fig = px.imshow(body, aspect="auto", color_continuous_scale="Blues")
    elif ctype == "折れ線":
        fig = px.line(long, x=d1, y=vcol, color="系列", markers=True)
    elif ctype == "横棒":
        fig = px.bar(long, y=d1, x=vcol, color="系列", orientation="h", barmode="group")
    else:
        fig = px.bar(long, x=d1, y=vcol, color="系列", barmode="relative" if ctype == "積み上げ棒" else "group")
    fig.update_layout(showlegend=d2 != NONE or ctype in ("円", "ドーナツ"))
    left.plotly_chart(fig)
    right.dataframe(pv.style.format("{:,.0f}"))
    right.download_button("表をCSV保存", pv.to_csv().encode("utf-8-sig"), "table.csv", "text/csv")

# ---------- 高度分析 ----------
with t3:
    a, b = st.columns(2)
    y = M["支出"].to_numpy(float)
    n = len(y)
    slope, icpt = np.polyfit(np.arange(n), y, 1) if n >= 2 else (0.0, y.mean())
    future = pd.period_range(M.index[-1], periods=4, freq="M").strftime("%Y-%m")[1:]
    fv = np.clip(icpt + slope * np.arange(n, n + 3), 0, None)
    fig = go.Figure()
    fig.add_scatter(x=M.index, y=y, name="実績", line_color="#d9480f")
    fig.add_scatter(x=M.index, y=pd.Series(y).rolling(3).mean(), name="3か月移動平均", line=dict(color="#2f4bd8", dash="dash"))
    fig.add_scatter(x=[M.index[-1], *future], y=[y[-1], *fv], name="予測", line=dict(color="#0e8f7e", dash="dot"))
    fig.update_layout(title="支出の予測(直線トレンド)", legend_orientation="h")
    a.plotly_chart(fig)
    bal, net = D["収入"].sum() - D["支出"].sum(), (M["収入"] - M["支出"]).mean()
    msg = f"トレンドは月あたり{yen(slope)}。今後3か月の支出予測は合計{yen(fv.sum())}。"
    if net < 0 < bal:
        msg += f" 平均収支が赤字({yen(net)}/月)のため、残高はあと約{bal / -net:.1f}か月で尽きる見込みです。"
    a.caption(msg)

    ct = D[D["支出"] > 0].groupby("項目")["支出"].sum().sort_values(ascending=False)
    cum = ct.cumsum() / ct.sum() * 100
    k80 = int((cum < 80).sum()) + 1
    fig = go.Figure()
    fig.add_bar(x=ct.index, y=ct.values, name="支出", marker_color=["#2f4bd8"] * k80 + ["#9aa6c4"] * (len(ct) - k80))
    fig.add_scatter(x=ct.index, y=cum.values, name="累積比率(%)", yaxis="y2", line_color="#d9480f")
    fig.update_layout(title="パレート分析", yaxis2=dict(overlaying="y", side="right", range=[0, 100]), legend_orientation="h")
    b.plotly_chart(fig)
    b.caption(f"上位{k80}項目で支出全体の約80%を占めます。見直すならまずここから。")

    heat = D[D["項目"].isin(ct.head(12).index)].pivot_table(index="項目", columns="月", values="支出", aggfunc="sum", fill_value=0)
    st.plotly_chart(px.imshow(heat, aspect="auto", color_continuous_scale="Oranges", title="項目 × 月のヒートマップ(支出)"))

    st.subheader("異常値・重複の検出")
    ex = D[D["支出"] > 0].copy()
    grp = ex.groupby("項目")["支出"]
    ex["z"] = (ex["支出"] - grp.transform("mean")) / grp.transform("std").replace(0, np.nan)
    ex["件数"] = grp.transform("size")
    out = ex[(ex["z"] >= 2) & (ex["件数"] >= 4)].assign(理由="項目平均から大きく外れた支出")
    dup = D[D.duplicated(["日付", "項目", "収入", "支出"], keep=False)].assign(理由="重複の可能性")
    res = pd.concat([out, dup])[["日付", "項目", "収入", "支出", "理由"]]
    st.dataframe(res) if len(res) else st.success("検出されませんでした。")

# ---------- データ ----------
with t4:
    st.dataframe(D.drop(columns=[]), hide_index=True)
