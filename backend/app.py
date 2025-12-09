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

