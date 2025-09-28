# backend/seed_data.py
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "payment_demo_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
txns = db["transactions"]

def seed(n=30):
    txns.delete_many({})  # clear for demo
    payers = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    payees = ["MerchantA", "MerchantB", "StoreX", "VendorY", "VendorZ"]
    channels = ["UPI", "NEFT", "RTGS", "IMPS"]
    statuses = ["Pending", "Success", "Failed"]
    now = datetime.utcnow()
    docs = []
    for i in range(n):
        doc = {
            "txn_id": f"TXN{100000+i}",
            "payer": random.choice(payers),
            "payee": random.choice(payees),
            "amount": round(random.uniform(10, 200000), 2),
            "channel": random.choice(channels),
            "status": random.choices(statuses, weights=[0.2, 0.6, 0.2])[0],
            "timestamp": now - timedelta(minutes=random.randint(0, 60*24)),
            "remarks": ""
        }
        docs.append(doc)
    txns.insert_many(docs)
    print(f"Inserted {len(docs)} transactions.")

if __name__ == "__main__":
    seed(60)
