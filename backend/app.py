from apiflask import APIFlask
from flask import request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required
)
import psycopg2
from psycopg2 import Error

app = APIFlask(__name__)

app.config["JWT_SECRET_KEY"] = "HEMMELIG_NOEGLE"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
jwt = JWTManager(app)

def get_connection():
    try:
        conn = psycopg2.connect(
            user="postgres",
            password="1234",
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
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if username != "SmartHealthTeam" or password != "Gruppe11B":
        return {"msg": "Invalid login"}, 401

    token = create_access_token(identity=username)
    return {"token": token}, 200

@app.get("/patients")
@jwt_required()
def get_patients():
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute("SELECT id, name, age FROM patients;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = [{"id": r[0], "name": r[1], "age": r[2]} for r in rows]
    return result, 200

@app.get("/patient/<int:pid>")
@jwt_required()
def get_patient(pid):
    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute("SELECT id, name, age FROM patients WHERE id=%s;", (pid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {"error": "Patient not found"}, 404
    return {"id": row[0], "name": row[1], "age": row[2]}, 200

@app.post("/add_patient")
@jwt_required()
def add_patient():
    data = request.json
    name = data.get("name")
    age = data.get("age")

    conn = get_connection()
    if not conn:
        return {"error": "DB connection failed"}, 500
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO patients (name, age) VALUES (%s, %s) RETURNING id;",
        (name, age)
    )
    new_id = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {"message": "Patient added", "id": new_id}, 201

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

if __name__ == "__main__":
    app.run(debug=True)
