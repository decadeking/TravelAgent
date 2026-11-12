# -*- coding: utf-8 -*-
import sqlite3, sys

path = r"c:\Users\decade\Desktop\TravelAgent\backend\test_travelagent.db"
c = sqlite3.connect(path)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
if "users" in tables:
    for row in c.execute("SELECT id,username,nickname,role,created_at FROM users"):
        print(row)
