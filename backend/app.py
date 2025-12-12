from apiflask import APIFlask, Schema
from apiflask.fields import String, Integer, Float
from flask import request, jsonify, Flask, render_template
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required
)
import psycopg2
from psycopg2 import Error
import re
import plotly.graph_objects as go
from plotly.io import to_html


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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/hjem")
def hjem():
    return render_template("hjem.html")

@app.route("/patient")
def patient():
    return render_template("patient.html")

@app.route("/observation")
def observation():
    return render_template("observation.html")

@app.route("/dashboard")
def dashboard():
    conn = get_connection()
    if not conn:
        return render_template("dashboard.html", error="DB connection failed")

    cur = conn.cursor()

    # --- Dropdown: patienter ---
    cur.execute("SELECT id, name, age, cpr_nummer FROM patients ORDER BY id ASC;")
    patient_rows = cur.fetchall()
    if not patient_rows:
        cur.close()
        conn.close()
        return render_template("dashboard.html", error="No patients found")

    patients = [{"id": p[0], "name": p[1], "age": p[2], "cpr_nummer": p[3]} for p in patient_rows]

    selected_patient_id = request.args.get("patient_id", type=int)
    if selected_patient_id is None:
        selected_patient_id = patients[0]["id"]

    valid_ids = {p["id"] for p in patients}
    if selected_patient_id not in valid_ids:
        selected_patient_id = patients[0]["id"]

    # --- Målinger (last 50) for valgt patient ---
    # VIGTIGT: her tager vi også batterier med til device-grafen
    cur.execute("""
        SELECT
            m.created_at,
            m.body_temperature,
            m.heart_rate,
            m.spo2,
            m.battery_controller,
            m.battery_sensor,
            m.battery_actuator,
            p.cpr_nummer
        FROM measurements m
        JOIN patients p ON p.id = m.patient_id
        WHERE m.patient_id = %s
        ORDER BY m.created_at DESC
        LIMIT 50;
    """, (selected_patient_id,))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    if not rows:
        return render_template(
            "dashboard.html",
            patients=patients,
            selected_patient_id=selected_patient_id,
            error="No measurements for selected patient yet"
        )

    # frem i tid
    rows = list(reversed(rows))

    times = [r[0] for r in rows]
    temps = [float(r[1]) if r[1] is not None else None for r in rows]
    hr    = [int(r[2]) if r[2] is not None else None for r in rows]
    spo2  = [int(r[3]) if r[3] is not None else None for r in rows]

    bat_ctrl = [float(r[4]) if r[4] is not None else None for r in rows]
    bat_sens = [float(r[5]) if r[5] is not None else None for r in rows]
    bat_act  = [float(r[6]) if r[6] is not None else None for r in rows]

    latest = rows[-1]
    latest_data = {
    "cpr_nummer": latest[7],
    "created_at": latest[0].strftime("%Y-%m-%d %H:%M"),
    "body_temperature": float(latest[1]) if latest[1] is not None else None,
    "heart_rate": int(latest[2]) if latest[2] is not None else None,
    "spo2": int(latest[3]) if latest[3] is not None else None,
    "battery_controller": float(latest[4]) if latest[4] is not None else None,
    "battery_sensor": float(latest[5]) if latest[5] is not None else None,
    "battery_actuator": float(latest[6]) if latest[6] is not None else None,
    }


    x0, x1 = times[0], times[-1]

    # =========================
    # FIG 1: VITALS (medical)
    # =========================
    fig_vitals = go.Figure()

    # “medical vibe”: let grøn zone for normal temp (36.1–37.5)
    fig_vitals.add_shape(
        type="rect", xref="x", yref="y",
        x0=x0, x1=x1, y0=36.1, y1=37.5,
        line=dict(width=0),
        fillcolor="rgba(0, 200, 0, 0.10)",
        layer="below"
    )

    fig_vitals.add_trace(go.Scatter(x=times, y=temps, mode="lines+markers", name="Temperature (°C)"))
    fig_vitals.add_trace(go.Scatter(x=times, y=hr,    mode="lines+markers", name="Heart rate (bpm)"))
    fig_vitals.add_trace(go.Scatter(x=times, y=spo2,  mode="lines+markers", name="SpO2 (%)"))

    fig_vitals.update_layout(
    title="Vitals",
    xaxis_title="Time",
    yaxis_title="Value",
    margin=dict(l=40, r=40, t=60, b=40),
    legend=dict(
        orientation="h",
        y=-0.25,
        x=0.5,
        xanchor="center",
        itemwidth=120
    ),
    height=380
    )


    # =========================
    # FIG 2: DEVICE HEALTH (battery)
    # =========================
    # FIG 2: DEVICE HEALTH (simple bars)
    fig_battery = go.Figure()

    labels = ["Controller", "Sensor", "Actuator"]
    values = [
        latest_data["battery_controller"],
        latest_data["battery_sensor"],
        latest_data["battery_actuator"]
    ]

    fig_battery.add_trace(go.Bar(x=labels, y=values, name="Battery"))

    fig_battery.update_layout(
    title="Device Health",
    xaxis_title="Device",
    yaxis_title="Batteri (%)",
    margin=dict(l=30, r=30, t=60, b=30),
    height=350,
    yaxis=dict(range=[0, 100])
    )

    # Kun include_plotlyjs én gang
    vitals_html = to_html(fig_vitals, full_html=False, include_plotlyjs="cdn")
    battery_html = to_html(fig_battery, full_html=False, include_plotlyjs=False)

    return render_template(
        "dashboard.html",
        patients=patients,
        selected_patient_id=selected_patient_id,
        latest=latest_data,
        vitals_html=vitals_html,
        battery_html=battery_html
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

