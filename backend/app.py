from apiflask import APIFlask, Schema
from apiflask.fields import String, Integer, Float
from flask import render_template, request, redirect, url_for, session
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required
)
import psycopg2
from psycopg2 import Error
import re
import plotly.graph_objects as go
from plotly.io import to_html

from functools import wraps


app = APIFlask(__name__)

app.secret_key = "9c8e4b3f7a1d0f0a8b6e3d4c5f9a2e7c1b4d8e6a0f3c2d9b7a6e5f4c3b2a1"
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

def web_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("web_login"))
        return fn(*args, **kwargs)
    return wrapper

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

@app.post("/api/login")
@app.input(LoginSchema)
def api_login(json_data):
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

@app.route("/")
@web_login_required
def index():
    return render_template("index.html")

@app.route("/hjem")
@web_login_required
def hjem():
    return render_template("hjem.html")

@app.route("/patient")
@web_login_required
def patient():
    return render_template("patient.html")

@app.route("/observation")
@web_login_required
def observation():
    return render_template("observation.html")

@app.route("/dashboard")
@web_login_required
def dashboard():
    conn = get_connection()
    if not conn:
        return render_template("dashboard.html", error="DB connection failed")

    cur = conn.cursor()
    cur.execute("""
        SELECT
            m.created_at,
            m.body_temperature,
            m.heart_rate,
            m.spo2,
            p.cpr_nummer
        FROM measurements m
        JOIN patients p ON p.id = m.patient_id
        ORDER BY m.created_at DESC
        LIMIT 50;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return render_template("dashboard.html", error="No measurements yet")

    # vend rækkefølgen så grafen går frem i tid
    rows = list(reversed(rows))

    times = [r[0] for r in rows]
    temps = [float(r[1]) if r[1] is not None else None for r in rows]
    hr    = [int(r[2]) if r[2] is not None else None for r in rows]
    spo2  = [int(r[3]) if r[3] is not None else None for r in rows]

    latest = rows[-1]
    latest_data = {
        "cpr_nummer": latest[4],
        "created_at": latest[0],
        "body_temperature": float(latest[1]) if latest[1] is not None else None,
        "heart_rate": int(latest[2]) if latest[2] is not None else None,
        "spo2": int(latest[3]) if latest[3] is not None else None,
    }

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=temps, mode="lines+markers", name="Temperature (°C)"))
    fig.add_trace(go.Scatter(x=times, y=hr, mode="lines+markers", name="Heart rate (bpm)"))
    fig.add_trace(go.Scatter(x=times, y=spo2, mode="lines+markers", name="SpO2 (%)"))

    fig.update_layout(
        title="Measurements (last 50)",
        xaxis_title="Time",
        yaxis_title="Value",
        margin=dict(l=30, r=30, t=50, b=30),
        legend=dict(orientation="h")
    )

    graph_html = to_html(fig, full_html=False, include_plotlyjs="cdn")

    return render_template(
        "dashboard.html",
        latest=latest_data,
        graph_html=graph_html
    )


    cur = conn.cursor()
    cur.execute("""
        SELECT
            m.created_at,
            m.body_temperature,
            m.heart_rate,
            m.spo2,
            p.cpr_nummer
        FROM measurements m
        JOIN patients p ON p.id = m.patient_id
        ORDER BY m.created_at DESC
        LIMIT 50;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return render_template("dashboard.html", error="No measurements yet")

    # vend rækkefølgen så grafen går frem i tid
    rows = list(reversed(rows))

    times = [r[0] for r in rows]
    temps = [float(r[1]) if r[1] is not None else None for r in rows]
    hr    = [int(r[2]) if r[2] is not None else None for r in rows]
    spo2  = [int(r[3]) if r[3] is not None else None for r in rows]

    latest = rows[-1]
    latest_data = {
        "cpr_nummer": latest[4],
        "created_at": latest[0],
        "body_temperature": float(latest[1]) if latest[1] is not None else None,
        "heart_rate": int(latest[2]) if latest[2] is not None else None,
        "spo2": int(latest[3]) if latest[3] is not None else None,
    }

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=temps, mode="lines+markers", name="Temperature (°C)"))
    fig.add_trace(go.Scatter(x=times, y=hr, mode="lines+markers", name="Heart rate (bpm)"))
    fig.add_trace(go.Scatter(x=times, y=spo2, mode="lines+markers", name="SpO2 (%)"))

    fig.update_layout(
        title="Measurements (last 50)",
        xaxis_title="Time",
        yaxis_title="Value",
        margin=dict(l=30, r=30, t=50, b=30),
        legend=dict(orientation="h")
    )

    graph_html = to_html(fig, full_html=False, include_plotlyjs="cdn")

    return render_template(
        "dashboard.html",
        latest=latest_data,
        graph_html=graph_html
    )



@app.route("/login", methods=["GET", "POST"])
def web_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        # Samme credentials som dit API-login
        if username != "SmartHealthTeam" or password != "Gruppe11B":
            return render_template("web_login.html", error="Forkert brugernavn eller kodeord")

        session["user"] = username
        return redirect(url_for("index"))

    return render_template("web_login.html")


@app.route("/logout")
def web_logout():
    session.clear()
    return redirect(url_for("web_login"))

@app.route("/login", methods=["GET", "POST"])
def web_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        # Samme credentials som dit API-login
        if username != "SmartHealthTeam" or password != "Gruppe11B":
            return render_template("web_login.html", error="Forkert brugernavn eller kodeord")

        session["user"] = username
        return redirect(url_for("index"))

    return render_template("web_login.html")


@app.route("/logout")
def web_logout():
    session.clear()
    return redirect(url_for("web_login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

