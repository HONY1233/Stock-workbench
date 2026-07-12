"""半导体图谱穿透分析：行业层 → 概念层 → 个股层 三级穿透。

由于东财板块成分股接口被封，采用预设产业链龙头股名单 + 同花顺板块历史 + 腾讯实时行情方案。
"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records


# ── 半导体产业链图谱（预设龙头股） ──────────────────────────────────────────

SEMICONDUCTOR_MAP = {
    "行业总览": {
        "行业板块": ["半导体"],
    },
    "上游-材料": {
        "概念板块": ["光刻胶", "第三代半导体"],
        "代表个股": {
            "沪硅产业": "688126",
            "立昂微": "605358",
            "安集科技": "688019",
            "江丰电子": "300666",
            "雅克科技": "002409",
            "南大光电": "300346",
            "晶瑞电材": "300655",
            "华特气体": "688268",
        },
    },
    "上游-设备": {
        "概念板块": ["光刻机"],
        "代表个股": {
            "北方华创": "002371",
            "中微公司": "688012",
            "拓荆科技": "688072",
            "芯源微": "688037",
            "长川科技": "300604",
            "华海清科": "688120",
            "万业企业": "600641",
            "至纯科技": "603690",
        },
    },
    "中游-设计": {
        "概念板块": ["芯片概念", "MCU芯片", "汽车芯片", "存储芯片"],
        "代表个股": {
            "韦尔股份": "603501",
            "兆易创新": "603986",
            "澜起科技": "688008",
            "卓胜微": "300782",
            "寒武纪": "688256",
            "海光信息": "688041",
            "紫光国微": "002049",
            "北京君正": "300223",
        },
    },
    "中游-制造": {
        "概念板块": [],
        "代表个股": {
            "中芯国际": "688981",
            "华虹公司": "688347",
            "华润微": "688396",
            "士兰微": "600460",
            "闻泰科技": "600745",
            "扬杰科技": "300373",
            "捷捷微电": "300623",
            "斯达半导": "603290",
        },
    },
    "下游-封测": {
        "概念板块": [],
        "代表个股": {
            "长电科技": "600584",
            "通富微电": "002156",
            "华天科技": "002185",
            "晶方科技": "603005",
            "甬矽电子": "688362",
            "利扬芯片": "688135",
        },
    },
    "下游-PCB": {
        "概念板块": ["PCB概念"],
        "代表个股": {
            "沪电股份": "002463",
            "深南电路": "002916",
            "生益科技": "600183",
            "鹏鼎控股": "002938",
            "东山精密": "002384",
            "胜宏科技": "300476",
        },
    },
}


def _tencent_quote_batch(codes):
    """批量查询腾讯实时行情。"""
    try:
        import urllib.request
        qt_codes = []
        for c in codes:
            cl = c.lower()
            if cl.startswith("sh") or cl.startswith("sz"):
                qt_codes.append(cl)
            else:
                if c[0] in ("6", "9") or c[:2] in ("68", "90"):
                    qt_codes.append("sh" + c)
                else:
                    qt_codes.append("sz" + c)
        url = "https://qt.gtimg.cn/q=" + ",".join(qt_codes)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        text = raw.decode("gbk", errors="replace")
        results = {}
        for seg in text.split(";"):
            seg = seg.strip()
            if not seg or "~" not in seg:
                continue
            eq_idx = seg.find("=")
            if eq_idx < 0:
                continue
            content = seg[eq_idx + 1:].strip('"').strip()
            fields = content.split("~")
            if len(fields) < 50:
                continue
            code = fields[2]
            results[code] = {
                "名称": fields[1],
                "现价": fields[3],
                "涨跌幅(%)": fields[32],
                "涨跌额": fields[31],
                "成交额(万)": fields[37],
                "换手率(%)": fields[38],
                "总市值(万)": fields[45],
            }
        return results
    except Exception:
        return {}


def _stock_hist_pct(code, date, lookback_days=10):
    """获取个股指定日期的涨跌幅（历史日线）。"""
    try:
        import datetime
        dt = datetime.datetime.strptime(date, "%Y%m%d")
        start = (dt - datetime.timedelta(days=lookback_days + 20)).strftime("%Y%m%d")
        end = date
        # 优先用 akshare stock_zh_a_hist（东方财富，稳定）
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        except Exception:
            # 兜底：新浪接口
            try:
                prefix = "sh" if (code[0] in ("6", "9") or code[:2] in ("68", "90")) else "sz"
                df = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", start_date=start, end_date=end, adjust="qfq")
            except Exception:
                return None
        if df is None or len(df) < 2:
            return None
        data = _df_to_records(df)
        # 统一字段名
        def _get(row, *keys):
            for k in keys:
                if k in row and row[k] is not None:
                    return row[k]
            return None

        target = None
        prev_close = None
        for i, row in enumerate(data):
            row_date = str(_get(row, "日期", "date", "trade_date") or "").replace("-", "")
            if row_date == date:
                target = row
                if i > 0:
                    prev_close = _get(data[i-1], "收盘", "close", "收盘价")
                break
        if target is None:
            target = data[-1]
            if len(data) >= 2:
                prev_close = _get(data[-2], "收盘", "close", "收盘价")
        close = _get(target, "收盘", "close", "收盘价") or 0
        if not prev_close:
            prev_close = 0
        pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
        amount = _get(target, "成交额", "amount") or 0
        turnover = _get(target, "换手率", "turnover") or ""
        # 涨跌幅直接用接口提供的
        pct_raw = _get(target, "涨跌幅")
        if pct_raw is not None:
            try:
                pct = round(float(pct_raw), 2)
            except (ValueError, TypeError):
                pass
        return {
            "收盘价": close,
            "涨跌幅": pct,
            "成交额": amount,
            "换手率": turnover,
        }
    except Exception:
        return None


def _sector_pct_change(name, date, lookback_days=5):
    """获取某板块指定日期的涨跌幅。"""
    try:
        import datetime
        dt = datetime.datetime.strptime(date, "%Y%m%d")
        start = (dt - datetime.timedelta(days=lookback_days + 10)).strftime("%Y%m%d")
        end = date
        # 尝试行业板块
        try:
            df = ak.stock_board_industry_index_ths(
                symbol=name, start_date=start, end_date=end,
            )
        except Exception:
            try:
                df = ak.stock_board_concept_index_ths(
                    symbol=name, start_date=start, end_date=end,
                )
            except Exception:
                return None
        if df is None or len(df) < 2:
            return None
        data = _df_to_records(df)
        # 找目标日期
        target = None
        prev_close = None
        for i, row in enumerate(data):
            row_date = str(row.get("日期", "")).replace("-", "")
            if row_date == date:
                target = row
                if i > 0:
                    prev_close = data[i-1].get("收盘价", 0)
                break
        if target is None:
            target = data[-1]
            if len(data) >= 2:
                prev_close = data[-2].get("收盘价", 0)
        close = target.get("收盘价", 0)
        pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
        return {
            "名称": name,
            "收盘价": close,
            "涨跌幅": pct,
            "成交额": target.get("成交额", 0),
        }
    except Exception:
        return None


def _sector_period_return(name, start_date, end_date):
    """获取板块区间涨跌幅。"""
    try:
        import datetime
        # 多取几天保证能找到前一日收盘价
        sdt = datetime.datetime.strptime(start_date, "%Y%m%d")
        s_start = (sdt - datetime.timedelta(days=10)).strftime("%Y%m%d")
        try:
            df = ak.stock_board_industry_index_ths(
                symbol=name, start_date=s_start, end_date=end_date,
            )
        except Exception:
            try:
                df = ak.stock_board_concept_index_ths(
                    symbol=name, start_date=s_start, end_date=end_date,
                )
            except Exception:
                return None
        if df is None or len(df) < 2:
            return None
        data = _df_to_records(df)
        # 找起始日附近和结束日
        start_close = None
        end_close = None
        for i, row in enumerate(data):
            rd = str(row.get("日期", "")).replace("-", "")
            if rd >= start_date and start_close is None:
                if i > 0:
                    start_close = data[i-1].get("收盘价", 0)
                else:
                    start_close = row.get("收盘价", 0)
            if rd == end_date or (rd < end_date and i == len(data)-1):
                end_close = row.get("收盘价", 0)
        if start_close and end_close:
            return round((end_close - start_close) / start_close * 100, 2)
        return None
    except Exception:
        return None


def register(mcp) -> list[str]:
    """注册半导体图谱分析工具。"""

    @mcp.tool(description="半导体图谱穿透分析：行业→概念→个股三级穿透，含涨跌幅、资金、龙头股表现")
    def semiconductor_map_analysis(
        date: str = "",
        period_days: int = 5,
        top_n: int = 10,
    ) -> str:
        """半导体产业链图谱穿透分析。

        三级穿透：
        L1 行业层 - 半导体行业整体表现与全行业排名
        L2 概念层 - 上游材料/设备、中游设计/制造、下游封测/PCB 各细分概念对比
        L3 个股层 - 产业链各环节龙头股实时表现、涨跌榜

        Args:
            date: 分析日期 YYYYMMDD，默认最新交易日
            period_days: 区间统计天数，默认 5 日
            top_n: 个股涨跌榜返回前 N 名，默认 10

        Returns:
            JSON 格式的穿透分析结果
        """
        try:
            import datetime
            if not date:
                date = datetime.date.today().strftime("%Y%m%d")

            # 计算区间起始日
            dt = datetime.datetime.strptime(date, "%Y%m%d")
            start_date = (dt - datetime.timedelta(days=period_days + 15)).strftime("%Y%m%d")

            result = {
                "date": date,
                "period_days": period_days,
                "levels": {},
            }

            # ── L1 行业层 ──
            print("L1 行业层分析中...")
            l1 = {}
            semi_info = _sector_pct_change("半导体", date)
            if semi_info:
                l1["半导体"] = semi_info
                period_ret = _sector_period_return("半导体", start_date, date)
                if period_ret is not None:
                    l1["半导体"][f"{period_days}日涨跌幅"] = period_ret

            # 全行业排名（取当天全部行业板块涨跌幅）
            try:
                df_list = ak.stock_board_industry_name_ths()
                sectors_data = _df_to_records(df_list)
                sector_pcts = []
                for sec in sectors_data:
                    name = sec.get("name") or sec.get("名称", "")
                    if not name:
                        continue
                    info = _sector_pct_change(name, date, lookback_days=5)
                    if info:
                        sector_pcts.append({
                            "板块": name,
                            "涨跌幅": info["涨跌幅"],
                            "收盘价": info["收盘价"],
                        })
                sector_pcts.sort(key=lambda x: x["涨跌幅"], reverse=True)
                semi_rank = None
                for i, s in enumerate(sector_pcts):
                    if s["板块"] == "半导体":
                        semi_rank = i + 1
                        break
                l1["全行业排名"] = f"{semi_rank}/{len(sector_pcts)}" if semi_rank else "未知"
                l1["前5行业"] = sector_pcts[:5]
                l1["后5行业"] = sector_pcts[-5:][::-1]
            except Exception as e:
                l1["排名_错误"] = str(e)[:100]

            result["levels"]["L1_行业层"] = l1

            # ── L2 概念层 ──
            print("L2 概念层分析中...")
            l2 = {}
            for segment, info in SEMICONDUCTOR_MAP.items():
                if segment == "行业总览":
                    continue
                concepts = info.get("概念板块", [])
                if not concepts:
                    continue
                seg_data = []
                for concept in concepts:
                    info2 = _sector_pct_change(concept, date)
                    if info2:
                        period_ret = _sector_period_return(concept, start_date, date)
                        if period_ret is not None:
                            info2[f"{period_days}日涨跌幅"] = period_ret
                        seg_data.append(info2)
                if seg_data:
                    seg_data.sort(key=lambda x: x["涨跌幅"], reverse=True)
                    l2[segment] = seg_data
            result["levels"]["L2_概念层"] = l2

            # ── L3 个股层 ──
            print("L3 个股层分析中...")
            l3 = {}
            all_stocks = []
            all_codes = []
            for segment, info in SEMICONDUCTOR_MAP.items():
                if segment == "行业总览":
                    continue
                stocks = info.get("代表个股", {})
                if not stocks:
                    continue
                codes = list(stocks.values())
                all_codes.extend(codes)
                all_stocks.extend([{"名称": n, "代码": c, "环节": segment} for n, c in stocks.items()])

            # 判断是否为今天（用实时行情）还是历史日期（用历史日线）
            import datetime
            today = datetime.date.today().strftime("%Y%m%d")
            is_today = (date == today)

            if is_today:
                # 实时行情
                quotes = _tencent_quote_batch(all_codes)
                for s in all_stocks:
                    code = s["代码"]
                    q = quotes.get(code, {})
                    s.update(q)
                    try:
                        s["涨跌幅"] = float(q.get("涨跌幅(%)", 0)) if q.get("涨跌幅(%)") else 0
                    except (ValueError, TypeError):
                        s["涨跌幅"] = 0
            else:
                # 历史日线
                for s in all_stocks:
                    code = s["代码"]
                    hist = _stock_hist_pct(code, date)
                    if hist:
                        s["收盘价"] = hist["收盘价"]
                        s["涨跌幅"] = hist["涨跌幅"]
                        s["成交额"] = hist.get("成交额", "")
                        s["换手率"] = hist.get("换手率", "")
                    else:
                        s["涨跌幅"] = 0
                        s["收盘价"] = 0

            # 按环节分组
            for segment in SEMICONDUCTOR_MAP:
                if segment == "行业总览":
                    continue
                seg_stocks = [s for s in all_stocks if s["环节"] == segment]
                seg_stocks.sort(key=lambda x: x.get("涨跌幅", 0), reverse=True)
                if seg_stocks:
                    l3[segment] = seg_stocks

            # 总涨跌榜
            all_valid = [s for s in all_stocks if s.get("现价") or s.get("收盘价")]
            all_valid.sort(key=lambda x: x.get("涨跌幅", 0), reverse=True)
            l3["总涨幅榜_TOP{}".format(top_n)] = all_valid[:top_n]
            l3["总跌幅榜_TOP{}".format(top_n)] = all_valid[-top_n:][::-1]

            # 统计
            up_count = sum(1 for s in all_valid if s.get("涨跌幅", 0) > 0)
            down_count = sum(1 for s in all_valid if s.get("涨跌幅", 0) < 0)
            flat_count = sum(1 for s in all_valid if s.get("涨跌幅", 0) == 0)
            l3["涨跌统计"] = {
                "总数": len(all_valid),
                "上涨": up_count,
                "下跌": down_count,
                "平盘": flat_count,
                "上涨比例": f"{up_count/len(all_valid)*100:.1f}%" if all_valid else "N/A",
            }

            result["levels"]["L3_个股层"] = l3

            return json.dumps({
                "ok": True,
                "date": date,
                "period_days": period_days,
                "data": result,
            }, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return ["semiconductor_map_analysis"]
