import sqlite3
con = sqlite3.connect("yt.db")
cur = con.cursor()

cur.execute("CREATE TABLE yt(text,time,author,channel,votes,photo,heart,reply,time_parsed,id)")
