from __future__ import annotations

from pathlib import Path

import pandas as pd
from datetime import datetime


def export_to_excel(rows: list[dict], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _FORMULA_PREFIXES = ("=", "+", "-", "@")
    sanitized = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES):
                clean[k] = "'" + v
            else:
                clean[k] = v
        sanitized.append(clean)
    # Normalize column names: strip BOM and surrounding whitespace
    if sanitized:
        cleaned_rows = []
        for row in sanitized:
            clean_row = {}
            for k, v in row.items():
                if isinstance(k, str):
                    new_k = k.lstrip("\ufeff").strip()
                else:
                    new_k = str(k)
                # format datetime-like values to ISO strings to avoid Excel locale/format issues
                if isinstance(v, datetime):
                    new_v = v.isoformat()
                else:
                    new_v = v
                clean_row[new_k] = new_v
            cleaned_rows.append(clean_row)
        df = pd.DataFrame(cleaned_rows)
    else:
        df = pd.DataFrame(sanitized)
    # If rows contain IDs only (user_id/slot_id/activity_id), try to map them to readable names
    try:
        cols = set(df.columns)
        if cols.intersection({"user_id", "slot_id", "activity_id"}):
            from app.infrastructure.repositories import UserRepository, TimeSlotRepository, ActivityRepository

            user_repo = UserRepository()
            slot_repo = TimeSlotRepository()
            activity_repo = ActivityRepository()

            user_map: dict[str, str] = {}
            slot_map: dict[str, str] = {}
            activity_map: dict[str, str] = {}

            if "user_id" in df.columns:
                try:
                    for uid in pd.Series(df["user_id"]).dropna().astype(str).unique():
                        u = user_repo.get_by_id(uid)
                        user_map[uid] = u.get("username") if u else uid
                except Exception:
                    pass

            if "slot_id" in df.columns:
                try:
                    for sid in pd.Series(df["slot_id"]).dropna().astype(str).unique():
                        s = slot_repo.get(sid)
                        if s:
                            name = s.get("name") or (s.get("start_time") and s.get("end_time") and f"{s.get('start_time')} ~ {s.get('end_time')}")
                            slot_map[sid] = name or sid
                        else:
                            slot_map[sid] = sid
                except Exception:
                    pass

            if "activity_id" in df.columns:
                try:
                    for aid in pd.Series(df["activity_id"]).dropna().astype(str).unique():
                        a = activity_repo.get(aid)
                        activity_map[aid] = a.get("name") if a else aid
                except Exception:
                    pass

            # build human-friendly rows
            readable_rows: list[dict] = []
            for _, row in df.iterrows():
                r = dict(row)
                uid = str(r.get("user_id", ""))
                sid = str(r.get("slot_id", ""))
                aid = str(r.get("activity_id", ""))
                new_row: dict = {
                    "用户ID": uid,
                    "用户名": user_map.get(uid, uid),
                    "时段ID": sid,
                    "时段名称": slot_map.get(sid, sid),
                    "活动ID": aid,
                    "活动名称": activity_map.get(aid, aid),
                }
                # keep other fields (created_at etc.) after these
                for k, v in r.items():
                    if k not in ("user_id", "slot_id", "activity_id"):
                        new_row[k] = v
                readable_rows.append(new_row)

            if readable_rows:
                df = pd.DataFrame(readable_rows)
    except Exception:
        # best-effort mapping; on any failure fall back to raw df
        pass

    suffix = path.suffix.lower()
    if suffix == ".csv":
        # CSV for Excel: include BOM so Excel on Windows recognizes UTF-8
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        # write xlsx explicitly with openpyxl engine
        df.to_excel(path, index=False, engine="openpyxl")
    # Diagnostic dump to help troubleshoot if Excel shows misaligned headers
    try:
        debug_path = Path("tmp/export_debug.txt")
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_path.open("w", encoding="utf-8") as fh:
            fh.write("COLUMNS:\n")
            fh.write(repr(list(df.columns)) + "\n\n")
            fh.write("FIRST_ROW:\n")
            if not df.empty:
                fh.write(repr(df.iloc[0].to_dict()) + "\n")
            else:
                fh.write("<empty>\n")
    except Exception:
        pass
