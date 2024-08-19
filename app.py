import os
import hmac
import json

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from pymongo import MongoClient
import hashlib
load_dotenv()

client = MongoClient(f"mongodb://{os.getenv('MONGODB_HOST')}:27017/")
db = client["lounge"]
collection = db["players"]

API_SECRET = os.getenv("API_SECRET")
PASS_SECRET = os.getenv("PASS_SECRET")

app = Flask(__name__)

cors = CORS(app, origins="*")

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["5 per minute"],
)

@app.errorhandler(RateLimitExceeded)
def ratelimit_exceeded(error):
    return jsonify({'error': 'Too Many Requests'}), 429

def verify_hmac(data: str, signature: str):
  hashed = hmac.new(API_SECRET.encode('utf-8'), data.encode(), digestmod=hashlib.sha256).hexdigest()
  return hashed == signature

@app.post("/api/passwd")
def passwd():
    payload = json.dumps(request.json).encode('utf-8')

    calculated_signature = f'sha256={hmac.new(PASS_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()}'

    header_signature = request.headers.get('X-Hub-Signature-256')

    def timing_safe_equals(a, b):
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= x ^ y
        return result == 0

    if timing_safe_equals(calculated_signature.encode('utf-8'), header_signature.encode('utf-8')):
        # do bot stuff here
        return jsonify({'message': 'Cool!'}), 200
    return jsonify({'error': f'nope: sig: {header_signature}, in-utf8: {header_signature.encode('utf-8')}'}), 400

@app.get("/api/leaderboard")
def get_data():
    data = list(collection.find({}, {"_id": 0}))
    return data

@app.post("/api/update")
def update_mmr():
    signature: str = request.headers.get('X-HMAC-Signature')
    data: list = request.json
    
    if not data or not signature:
        return jsonify({'error': 'Missing data or signature'}), 400

    if not verify_hmac(str(data), signature):
        return jsonify({'error': 'Invalid signature'}), 403
    
    for item in data:
        name: str = item[0]
        mmr: int = item[1]
        
        if type(name) != str or type(mmr) != int:
            return jsonify({'error': 'Invalid Data Format'}), 400 
        
        current_mmr: int = collection.find_one({"name": name})['mmr']

        collection.update_one({"name": name}, {"$set": {"mmr": mmr}})
        collection.update_one({"name": name}, {"$push": {"history": mmr - current_mmr}})
        collection.update_one({"name": name}, {"$inc": {"wins" if mmr > current_mmr else "losses": 1}})

    return jsonify({'message': 'Data submitted successfully'}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0")
