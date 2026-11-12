# -*- coding: utf-8 -*-
import sqlite3, glob, os

roots = [r"c:\Users\decade\Desktop\TravelAgent\backend"]
for path in glob.glob(os.path.join(roots[0], "**", "*.db"), recursive=True):
    try:
        c = sqlite3.connect(path)
        rows = c.execute(
            "SELECT p.id,p.user_id,u.username,u.nickname,p.title,p.created_at "
            "FROM posts p JOIN users u ON u.id=p.user_id "
            "WHERE p.title LIKE '%成都周末%' OR u.nickname LIKE '%成晓宇%'"
        ).fetchall()
        print(path, "->", rows if rows else "无匹配")
    except Exception as e:
        print(path, "err:", e)
