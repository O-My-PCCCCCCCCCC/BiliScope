"""用途分类规则：按 B 站分区(tname) 兜底，免费、本地、幂等。"""
from __future__ import annotations

import sqlite3

# 优先级从高到低，tname 子串匹配第一个命中
TNAME_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("学习提升", ("知识", "科技", "校园", "职场", "教育", "纪录片", "教学", "数码", "编程", "科普", "课程", "学堂")),
    ("资讯", ("资讯", "时政", "社会", "环球", "新闻", "热点")),
    ("生活实用", ("美食", "时尚", "汽车", "运动", "旅行", "家居", "健康", "萌宠", "购物", "测评", "健身", "修理", "技巧")),
    ("娱乐消遣", ("音乐", "游戏", "影视", "娱乐", "鬼畜", "番剧", "动画", "国创", "舞蹈", "搞笑",
                 "日常", "小剧场", "综艺", "明星", "电影", "电视剧", "生活", "动物圈", "手工", "绘画", "翻唱", "直播")),
]


def categorize_by_tname(tname: str) -> str:
    """按分区返回用途类别；规则未命中返回「其他」。"""
    tname = (tname or "").strip()
    if not tname:
        return "其他"
    for category, keywords in TNAME_RULES:
        if any(k in tname for k in keywords):
            return category
    return "其他"


def reclassify_others(conn: sqlite3.Connection) -> int:
    """把 video_analysis 里 category='其他' 且分区能命中规则的重新归类。返回更新条数。"""
    rows = conn.execute(
        """SELECT va.bvid, v.tname FROM video_analysis va
           JOIN videos v ON va.bvid = v.bvid
           WHERE va.category IS NULL OR va.category = '其他'"""
    ).fetchall()
    n = 0
    for r in rows:
        cat = categorize_by_tname(r["tname"])
        if cat != "其他":
            conn.execute("UPDATE video_analysis SET category = ? WHERE bvid = ?", (cat, r["bvid"]))
            n += 1
    conn.commit()
    return n
