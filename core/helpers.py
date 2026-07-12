"""数据处理工具函数。"""
from __future__ import annotations
import json
from typing import Optional

import pandas as pd


def _safe_json(val):
    """将值安全转换为 JSON 可序列化类型。"""
    import numpy as np
    import datetime as _dt
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, (np.ndarray, list, tuple)):
        return [_safe_json(v) for v in val]
    if isinstance(val, dict):
        return {k: _safe_json(v) for k, v in val.items()}
    if isinstance(val, (pd.Timestamp,)):
        try:
            if pd.isna(val):
                return None
            return str(val.date())
        except Exception:
            return str(val)
    if isinstance(val, (_dt.date, _dt.datetime)):
        try:
            return str(val.date())
        except Exception:
            return str(val)
    if hasattr(val, 'item') and not isinstance(val, (str, bytes)):
        try:
            scalar = val.item()
            if isinstance(scalar, float) and pd.isna(scalar):
                return None
            return scalar
        except Exception:
            return str(val)
    return val


def _df_to_records(df: pd.DataFrame, limit: Optional[int] = None) -> list[dict]:
    """将 DataFrame 转为字典列表，处理 NaN 值。"""
    if df is None or df.empty:
        return []
    if limit and len(df) > limit:
        df = df.tail(limit)
    data = []
    for _, row in df.iterrows():
        item = {}
        for col in df.columns:
            item[col] = _safe_json(row[col])
        data.append(item)
    return data


def _json_ok(data, source: str = "", count: int | None = None, **extra) -> str:
    """构造成功返回 JSON。"""
    if count is None:
        count = len(data) if isinstance(data, list) else 0
    resp = {"ok": True, "source": source, "count": count, "data": data}
    resp.update(extra)
    return json.dumps(resp, ensure_ascii=False)


def _json_fail(error: str, **extra) -> str:
    """构造失败返回 JSON。"""
    resp = {"ok": False, "error": error}
    resp.update(extra)
    return json.dumps(resp, ensure_ascii=False)
