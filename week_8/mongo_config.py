# mongo_config.py
from mongoengine import connect

def init_mongo():
    connect(
        db="library",
        host="mongodb+srv://22028118:30012004@cluster0.sb7z5xv.mongodb.net/?appName=Cluster0",
        alias="default"
    )
