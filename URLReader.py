# -*- coding: utf-8 -*-
"""
Created on Fri Dec 15 21:22:23 2017
BOOTING UP SQL DATABASE:
Win + R
Run services.msc
Right-click on MySQL57
Start the service.
host="localhost",
user="root"
passwd="RootoftheS3qu3l"
,db='firstDB')
TABLE = firstTable

@author: Erik
"""
import pymysql
import urllib.request

user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'

url = "https://bitcointicker.co/"
headers={'User-Agent':user_agent,} 

request=urllib.request.Request(url,None,headers) #The assembled request
response = urllib.request.urlopen(request)
data = response.read().decode() # The data u need
identifier = "<input id=exchange_rate type=hidden value="
f = data.rfind('"time":')
print(data[f+29:f+80])

conn = pymysql.connect(host="localhost",user="root",passwd="RootoftheS3qu3l",db='firstDB')
cur = conn.cursor()
cur.execute("SELECT * FROM firstTable")
for data in cur:
    print(data)
conn.close()