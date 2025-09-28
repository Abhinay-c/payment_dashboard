# backend/app.py
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os

# Configuration - change MONGO_URI to your MongoDB connection string
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "payment_demo_db")

app = Flask(__name__, template_folder="templates")
CORS(app)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
txns = db["transactions"]
edits = db["edits"]

# Helper: convert Mongo doc -> JSON-serializable dict
def doc_to_json(doc):
    if not doc:
        return None
    out = {k: v for k, v in doc.items()}
    out["_id"] = str(out["_id"])
    return out

@app.route("/")
def index():
    # Manager web dashboard
    return render_template("dashboard.html")

# API: list transactions (with optional query params)
@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    q = {}
    # support searching by txn_id, payer, payee, status
    txn_id = request.args.get("txn_id")
    payer = request.args.get("payer")
    payee = request.args.get("payee")
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))

    if txn_id:
        q["txn_id"] = txn_id
    if payer:
        q["payer"] = {"$regex": payer, "$options": "i"}
    if payee:
        q["payee"] = {"$regex": payee, "$options": "i"}
    if status:
        q["status"] = status

    cursor = txns.find(q).sort("timestamp", -1).limit(limit)
    data = [doc_to_json(d) for d in cursor]
    return jsonify(data), 200

# API: get single transaction by txn_id
@app.route("/api/transactions/<txn_id>", methods=["GET"])
def get_transaction(txn_id):
    doc = txns.find_one({"txn_id": txn_id})
    if not doc:
        return jsonify({"error": "Transaction not found"}), 404
    return jsonify(doc_to_json(doc)), 200

# API: update allowed fields for a transaction (PUT)
@app.route("/api/transactions/<txn_id>", methods=["PUT"])
def update_transaction(txn_id):
    payload = request.get_json(force=True)
    allowed_fields = {"status", "amount", "payee", "channel", "remarks", "operator"}
    update = {}
    for k, v in payload.items():
        if k in allowed_fields:
            update[k] = v

    if not update:
        return jsonify({"error": "No updatable fields provided"}), 400

    # Fetch existing doc for audit
    existing = txns.find_one({"txn_id": txn_id})
    if not existing:
        return jsonify({"error": "Transaction not found"}), 404

    # Build patch and log each changed field
    changes = []
    for k, v in update.items():
        old = existing.get(k)
        if old != v:
            changes.append({
                "txn_id": txn_id,
                "field": k,
                "old_value": old,
                "new_value": v,
                "edited_by": payload.get("operator", "operator_unknown"),
                "edited_at": datetime.utcnow()
            })

    if changes:
        # apply update
        txns.update_one({"txn_id": txn_id}, {"$set": update})
        # insert edits
        for c in changes:
            edits.insert_one(c)

    # Return updated document
    updated = txns.find_one({"txn_id": txn_id})
    return jsonify(doc_to_json(updated)), 200

# API: seed endpoint (convenience) - BE CAREFUL on prod; here for demo
@app.route("/api/seed", methods=["POST"])
def seed_endpoint():
    # optional: accept count or use default sample data
    sample_count = int(request.json.get("count", 10)) if request.json else 10
    from random import choice, randint
    channels = ["UPI", "NEFT", "RTGS", "IMPS"]
    statuses = ["Pending", "Success", "Failed"]
    sample = []
    for i in range(sample_count):
        txn = {
            "txn_id": f"TXN{100000 + randint(0, 899999)}",
            "payer": choice(["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]),
            "payee": choice(["MerchantA", "MerchantB", "StoreX", "VendorY"]),
            "amount": round(randint(100, 200000) + randint(0,99)/100, 2),
            "channel": choice(channels),
            "status": choice(statuses),
            "timestamp": datetime.utcnow(),
            "remarks": ""
        }
        sample.append(txn)
    txns.insert_many(sample)
    return jsonify({"inserted": len(sample)}), 201

# API: stats for manager dashboard
@app.route("/api/stats", methods=["GET"])
def stats():
    # total count and total volume (today)
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline_total = [
        {"$match": {"timestamp": {"$gte": today_start}}},
        {"$group": {"_id": None, "total_count": {"$sum": 1}, "total_volume": {"$sum": "$amount"}}}
    ]
    tot = list(txns.aggregate(pipeline_total))
    total_count = tot[0]["total_count"] if tot else 0
    total_volume = tot[0]["total_volume"] if tot else 0.0

    # channel split
    pipeline_channel = [
        {"$match": {"timestamp": {"$gte": today_start}}},
        {"$group": {"_id": "$channel", "count": {"$sum": 1}, "volume": {"$sum": "$amount"}}}
    ]
    channel_data = list(txns.aggregate(pipeline_channel))

    # status split
    pipeline_status = [
        {"$match": {"timestamp": {"$gte": today_start}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    status_data = list(txns.aggregate(pipeline_status))

    # recent edits (last N)
    recent_edits_cursor = edits.find().sort("edited_at", -1).limit(10)
    recent_edits = []
    for e in recent_edits_cursor:
        e2 = {k: v for k, v in e.items()}
        e2["_id"] = str(e2["_id"])
        # format datetime
        if isinstance(e2.get("edited_at"), datetime):
            e2["edited_at"] = e2["edited_at"].isoformat() + "Z"
        recent_edits.append(e2)

    return jsonify({
        "total_count": total_count,
        "total_volume": total_volume,
        "channel_data": channel_data,
        "status_data": status_data,
        "recent_edits": recent_edits
    }), 200

# API: recent transactions (for quick feed)
@app.route("/api/recent", methods=["GET"])
def recent():
    cursor = txns.find().sort("timestamp", -1).limit(20)
    data = [doc_to_json(d) for d in cursor]
    return jsonify(data), 200

if __name__ == "__main__":
    print(f"Using MongoDB URI: {MONGO_URI}, DB: {DB_NAME}")
    app.run(host="127.0.0.1", port=5000, debug=True)
