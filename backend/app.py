from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from storage import read_json, write_json
from datetime import timedelta

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = "MEGET_HEMMELIG_NOGLE"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
jwt = JWTManager(app)

@app.post("/login")
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if username != "SmartHealthTeam" or password != "Gruppe11B":
        return jsonify({"msg": "Invalid login"}), 401

    token = create_access_token(identity=username)
    return jsonify({"token": token}), 200

@app.get("/patients")
@jwt_required()
def get_patients():
    data = read_json()
    return jsonify(data), 200



