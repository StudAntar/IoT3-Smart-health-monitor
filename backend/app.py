from apiflask import APIFlask, Schema
from apiflask.fields import String, Integer, Float
from flask import request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required
)
import psycopg2
from psycopg2 import Error
import re

app = APIFlask(__name__)

app.config["DEVICE_TOKEN"] = "ESP_32"
app.config["JWT_SECRET_KEY"] = "HEMMELIG_NOEGLE"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
jwt = JWTManager(app)

CPR_PATTERN = re.compile(r"^\d{6}-?\d{4}$")


def is_valid_cpr(cpr: str) -> bool:
    """
    Validerer at CPR-nummeret har formatet:
    - DDMMYY-XXXX eller
    - DDMMYYXXXX
    """
    if not isinstance(cpr, str):
        return False

    if not CPR_PATTERN.match(cpr):
        return False

    return True


class LoginSchema(Schema):
    username = String(required=True)
    password = String(required=True)

class PatientSchema(Schema):
    name = String(required=True)
    age = Integer(required=True)
    cpr_nummer = String(required=True)

class MeasurementSchema(Schema):
    cpr_nummer         = String(required=True)
    body_temperature   = Float(required=True)
    heart_rate         = Integer(required=True)
    spo2               = Integer(required=True)
    battery_controller = Float(required=True)
    battery_sensor     = Float(required=True)
    battery_actuator   = Float(required=True)


def get_connection():
    try:
        conn = psycopg2.connect(
            user="postgres",
            password="Darbi1234",
            host="127.0.0.1",
            port="5432",
            database="laege_klinik"
        )
        conn.autocommit = True
        return conn
    except Error as e:
        print("Fejl i DB:", e)
        return None

@app.post("/login")
@app.input(LoginSchema)
def login(json_data):
    username = json_data["username"]
    password = json_data["password"]

    if username != "SmartHealthTeam" or password != "Gruppe11B":
        return {"msg": "Invalid login"}, 401

    token = create_access_token(identity=username)
    return {"token": token}, 200

@app.post("/add_patient")
@jwt_required()
@app.input(PatientSchema)
def add_patient(json_data):
    name = json_data["name"]
    age = json_data["age"]
    cpr_nummer = json_data["cpr_nummer"]

    # CPR-format tjek
    if not is_valid_cpr(cpr_nummer):
        return {"error": "Ugyldigt CPR-format"}, 400

    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500

    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO patients (name, age, cpr_nummer) VALUES (%s, %s, %s) RETURNING id;",
            (name, age, cpr_nummer)
        )
        new_id = cur.fetchone()[0]
    except Error as e:
        cur.close()
        conn.close()
        # fx hvis CPR allerede findes
        return {"error": f"DB error: {e}"}, 400

    cur.close()
    conn.close()

    return {"message": "Patient added", "id": new_id, "cpr_nummer": cpr_nummer}, 201


@app.get("/patients")
@jwt_required()
def get_patients():
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, cpr_nummer FROM patients;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = [
        {"id": r[0], "name": r[1], "age": r[2], "cpr_nummer": r[3]}
        for r in rows
    ]
    return result, 200

@app.get("/patient/<int:pid>")
@jwt_required()
def get_patient(pid):
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, cpr_nummer FROM patients WHERE id=%s;", (pid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {"error": "Patient not found"}, 404
    return {"id": row[0], "name": row[1], "age": row[2], "cpr_nummer": row[3]}, 200


@app.delete("/patient/<int:pid>")
@jwt_required()
def delete_patient(pid):
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute("DELETE FROM patients WHERE id=%s RETURNING id;", (pid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {"error": "Patient not found"}, 404
    return {"message": "Patient deleted"}, 200

@app.post("/api/measurements")
@app.input(MeasurementSchema)
def add_measurement(json_data):
    # Simpel device-auth (kun styreenheden må sende)
    device_token = request.headers.get("X-DEVICE-TOKEN")
    if device_token != app.config["DEVICE_TOKEN"]:
        return {"msg": "Invalid device token"}, 401

    cpr_nummer        = json_data["cpr_nummer"]
    body_temperature   = json_data["body_temperature"]
    heart_rate         = json_data["heart_rate"]
    spo2               = json_data["spo2"]
    battery_controller = json_data["battery_controller"]
    battery_sensor     = json_data["battery_sensor"]
    battery_actuator   = json_data["battery_actuator"]

    # CPR-format tjek
    if not is_valid_cpr(cpr_nummer):
        return {"error": "Ugyldigt CPR-format"}, 400

    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500

    cur = conn.cursor()

    # Slå patient_id op via CPR
    cur.execute(
        "SELECT id FROM patients WHERE cpr_nummer = %s;",
        (cpr_nummer,)
    )
    patient_row = cur.fetchone()
    if not patient_row:
        cur.close()
        conn.close()
        return {"error": "Patient med dette CPR findes ikke"}, 404

    patient_id = patient_row[0]

    # Indsæt måling på det fundne patient_id
    cur.execute(
        """
        INSERT INTO measurements (
            patient_id,
            body_temperature,
            heart_rate,
            spo2,
            battery_controller,
            battery_sensor,
            battery_actuator
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at;
        """,
        (
            patient_id,
            body_temperature,
            heart_rate,
            spo2,
            battery_controller,
            battery_sensor,
            battery_actuator
        )
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return {
        "message": "Measurement added",
        "id": row[0],
        "created_at": row[1].isoformat(),
        "cpr_nummer": cpr_nummer
    }, 201

@app.get("/api/measurements")
@jwt_required()
def get_all_measurements():
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500

    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            patient_id,
            body_temperature,
            heart_rate,
            spo2,
            battery_controller,
            battery_sensor,
            battery_actuator,
            created_at
        FROM measurements
        ORDER BY created_at DESC;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "patient_id": r[1],
            "body_temperature": float(r[2]) if r[2] is not None else None,
            "heart_rate": r[3],
            "spo2": r[4],
            "battery_controller": float(r[5]) if r[5] is not None else None,
            "battery_sensor": float(r[6]) if r[6] is not None else None,
            "battery_actuator": float(r[7]) if r[7] is not None else None,
            "created_at": r[8].isoformat()
        })

    return result, 200



@app.get("/api/measurements/<int:patient_id>")
@jwt_required()
def get_measurements_for_patient(patient_id):
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500

    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            patient_id,
            body_temperature,
            heart_rate,
            spo2,
            battery_controller,
            battery_sensor,
            battery_actuator,
            created_at
        FROM measurements
        WHERE patient_id = %s
        ORDER BY created_at DESC;
    """, (patient_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "patient_id": r[1],
            "body_temperature": float(r[2]) if r[2] is not None else None,
            "heart_rate": r[3],
            "spo2": r[4],
            "battery_controller": float(r[5]) if r[5] is not None else None,
            "battery_sensor": float(r[6]) if r[6] is not None else None,
            "battery_actuator": float(r[7]) if r[7] is not None else None,
            "created_at": r[8].isoformat()
        })

    return result, 200



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

