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


@app.get("/patient/<int:pid>")
@jwt_required()
def get_patient(pid):
    data = read_json()
    for p in data:
        if p.get("id") == pid:
            return jsonify(p), 200
    return jsonify({"error": "Patient not found"}), 404


@app.post("/add_patient")
@jwt_required()
def add_patient():
    new_patient = request.get_json()
    data = read_json()

    new_patient["id"] = len(data) + 1

    data.append(new_patient)
    write_json(data)

    return jsonify({"message": "Patient added", "patient": new_patient}), 201

@app.delete("/patient/<int:pid>")
@jwt_required()
def delete_patient(pid):
    data = read_json()
    new_data = [p for p in data if p.get("id") != pid]

    if len(new_data) == len(data):
        return jsonify({"error": "Patient not found"}), 404

    write_json(new_data)
    return jsonify({"message": "Patient deleted"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
