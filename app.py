import os
import re
import secrets
import string
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# In-memory storage for stateful OTP tracking
# Structure: { reference_id: { "identifier": str, "otp": str, "expires_at": float, "attempts_left": int, "created_at": str } }
otp_store = {}
SERVICE_START_TIME = time.time()


def cleanup_expired_otps():
    """Helper to periodically clean up expired OTP records from memory."""
    now = time.time()
    expired_keys = [ref for ref, data in otp_store.items() if data["expires_at"] < now]
    for ref in expired_keys:
        otp_store.pop(ref, None)


# ---------------------------------------------------------
# Custom Error Handlers (Consistent JSON responses)
# ---------------------------------------------------------
@app.errorhandler(400)
def bad_request(error):
    return jsonify({
        "success": False,
        "error": "Bad Request",
        "message": getattr(error, "description", "The request could not be understood or was missing required parameters.")
    }), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Not Found",
        "message": getattr(error, "description", "The requested resource or endpoint was not found.")
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "error": "Method Not Allowed",
        "message": "The HTTP method used is not supported for this endpoint."
    }), 405


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({
        "success": False,
        "error": "Internal Server Error",
        "message": "An unexpected error occurred while processing your request."
    }), 500


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Embedded interactive API explorer and documentation UI."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint to verify service connectivity and operational status.
    """
    cleanup_expired_otps()
    uptime_seconds = int(time.time() - SERVICE_START_TIME)
    return jsonify({
        "service": "QuickOTP Microservice",
        "status": "UP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "active_otps": len(otp_store),
        "version": "1.0.0"
    }), 200


@app.route("/api/otp/generate-simple", methods=["GET"])
def generate_simple_otp():
    """
    GET /api/otp/generate-simple?digits=6&type=numeric
    Quick, stateless OTP generator for lightweight peer integrations.
    """
    digits_raw = request.args.get("digits", "6")
    otp_type = request.args.get("type", "numeric").lower()

    try:
        digits = int(digits_raw)
    except ValueError:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Query parameter 'digits' must be an integer between 4 and 10."
        }), 400

    if digits < 4 or digits > 10:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Query parameter 'digits' must be between 4 and 10."
        }), 400

    if otp_type == "numeric":
        characters = string.digits
    elif otp_type == "alphanumeric":
        characters = string.ascii_uppercase + string.digits
    elif otp_type == "alpha":
        characters = string.ascii_uppercase
    else:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Query parameter 'type' must be 'numeric', 'alpha', or 'alphanumeric'."
        }), 400

    otp = "".join(secrets.choice(characters) for _ in range(digits))

    return jsonify({
        "success": True,
        "otp": otp,
        "digits": digits,
        "type": otp_type,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }), 200


@app.route("/api/otp/generate", methods=["POST"])
def generate_stateful_otp():
    """
    POST /api/otp/generate
    Generates a secure stateful OTP tied to an identifier (email/phone).
    Request body (JSON):
    {
        "identifier": "student@university.edu",
        "digits": 6,
        "expiry_seconds": 300,
        "type": "numeric"
    }
    """
    cleanup_expired_otps()

    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Content-Type must be 'application/json' and request body must contain valid JSON."
        }), 400

    body = request.get_json()
    identifier = body.get("identifier")
    digits = body.get("digits", 6)
    expiry_seconds = body.get("expiry_seconds", 300)
    otp_type = body.get("type", "numeric").lower()

    # Validation
    if not identifier or not isinstance(identifier, str) or not identifier.strip():
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'identifier' is required (e.g., student email or phone number)."
        }), 400

    identifier = identifier.strip()

    if not isinstance(digits, int) or digits < 4 or digits > 10:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'digits' must be an integer between 4 and 10."
        }), 400

    if not isinstance(expiry_seconds, int) or expiry_seconds < 30 or expiry_seconds > 1800:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'expiry_seconds' must be an integer between 30 and 1800 seconds (30s - 30m)."
        }), 400

    if otp_type == "numeric":
        characters = string.digits
    elif otp_type == "alphanumeric":
        characters = string.ascii_uppercase + string.digits
    elif otp_type == "alpha":
        characters = string.ascii_uppercase
    else:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'type' must be 'numeric', 'alpha', or 'alphanumeric'."
        }), 400

    # Secure OTP generation
    otp_code = "".join(secrets.choice(characters) for _ in range(digits))
    reference_id = f"ref_{secrets.token_hex(8)}"
    now = time.time()
    expires_at = now + expiry_seconds

    otp_store[reference_id] = {
        "identifier": identifier,
        "otp": otp_code,
        "expires_at": expires_at,
        "attempts_left": 3,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    return jsonify({
        "success": True,
        "message": f"OTP generated successfully for {identifier}.",
        "reference_id": reference_id,
        "otp": otp_code,  # In production helper/dev mode, returned for convenience
        "identifier": identifier,
        "digits": digits,
        "expires_in_seconds": expiry_seconds,
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "max_attempts": 3
    }), 201


@app.route("/api/otp/verify", methods=["POST"])
def verify_otp():
    """
    POST /api/otp/verify
    Verifies a user-supplied OTP against the stored reference_id.
    Request body (JSON):
    {
        "reference_id": "ref_...",
        "otp": "492018"
    }
    """
    cleanup_expired_otps()

    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Content-Type must be 'application/json' and request body must contain valid JSON."
        }), 400

    body = request.get_json()
    reference_id = body.get("reference_id")
    supplied_otp = body.get("otp")

    if not reference_id or not isinstance(reference_id, str):
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'reference_id' is required."
        }), 400

    if not supplied_otp or not isinstance(supplied_otp, str):
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "Field 'otp' is required."
        }), 400

    record = otp_store.get(reference_id)

    if not record:
        return jsonify({
            "success": False,
            "error": "Not Found",
            "message": "Invalid or expired reference ID. Please request a new OTP."
        }), 404

    now = time.time()
    if now > record["expires_at"]:
        otp_store.pop(reference_id, None)
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": "OTP has expired. Please request a new OTP."
        }), 400

    # Decrement attempt counter
    record["attempts_left"] -= 1

    # Check match
    if secrets.compare_digest(record["otp"], supplied_otp.strip()):
        # OTP is correct -> invalidate immediately to prevent replay attacks
        otp_store.pop(reference_id, None)
        return jsonify({
            "success": True,
            "verified": True,
            "identifier": record["identifier"],
            "message": "OTP verified successfully! Authentication token granted."
        }), 200

    # Incorrect OTP
    if record["attempts_left"] <= 0:
        otp_store.pop(reference_id, None)
        return jsonify({
            "success": False,
            "verified": False,
            "error": "Too Many Failed Attempts",
            "message": "Maximum verification attempts exceeded. This OTP has been invalidated."
        }), 400

    return jsonify({
        "success": False,
        "verified": False,
        "error": "Invalid OTP",
        "message": f"Incorrect OTP code provided. You have {record['attempts_left']} attempt(s) remaining.",
        "attempts_left": record["attempts_left"]
    }), 400


# ---------------------------------------------------------
# Embedded Interactive Web Interface & Docs
# ---------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QuickOTP Microservice - Interactive API Explorer</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(23, 32, 54, 0.7);
      --card-border: rgba(99, 102, 241, 0.2);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --accent: #10b981;
      --error: #ef4444;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --code-bg: #030712;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    body {
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 75%);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 1rem;
    }
    .container { max-width: 1000px; margin: 0 auto; }
    header { text-align: center; margin-bottom: 2.5rem; }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: rgba(99, 102, 241, 0.2);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.4);
      margin-bottom: 0.75rem;
    }
    h1 { font-size: 2.4rem; font-weight: 800; letter-spacing: -0.025em; margin-bottom: 0.5rem; }
    p.subtitle { color: var(--text-muted); font-size: 1.1rem; max-width: 650px; margin: 0 auto; }
    
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    @media(max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 1rem;
      padding: 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }
    .card h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between; }
    .method {
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 0.375rem;
      font-weight: 700;
    }
    .method.get { background: #064e3b; color: #34d399; }
    .method.post { background: #1e3a8a; color: #60a5fa; }
    
    .form-group { margin-bottom: 1rem; }
    label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.35rem; }
    input, select {
      width: 100%;
      padding: 0.65rem 0.85rem;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 0.5rem;
      color: #fff;
      font-size: 0.9rem;
    }
    input:focus, select:focus { outline: none; border-color: var(--primary); ring: 2px solid var(--primary); }
    
    button {
      width: 100%;
      padding: 0.75rem;
      border-radius: 0.5rem;
      border: none;
      background: var(--primary);
      color: #fff;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    button:hover { background: var(--primary-hover); transform: translateY(-1px); }
    button:active { transform: translateY(0); }
    
    .response-area {
      margin-top: 1rem;
      background: var(--code-bg);
      border-radius: 0.5rem;
      padding: 1rem;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 0.85rem;
      color: #38bdf8;
      overflow-x: auto;
      max-height: 220px;
      white-space: pre-wrap;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .status-badge { font-weight: bold; margin-bottom: 0.5rem; display: block; }
    .status-200, .status-201 { color: var(--accent); }
    .status-400, .status-404 { color: var(--error); }
    
    footer { text-align: center; margin-top: 3rem; color: var(--text-muted); font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="badge">🚀 Peer-Utility Microservice</div>
      <h1>QuickOTP Helper Microservice</h1>
      <p class="subtitle">A secure, reusable REST microservice providing one-time password generation, expiration TTL, and brute-force protected verification for peer projects.</p>
    </header>

    <div class="grid">
      <!-- Health Check -->
      <div class="card">
        <h2><span>Server Health</span> <span class="method get">GET /api/health</span></h2>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">Checks live microservice status, uptime, and active in-memory OTP count.</p>
        <button id="btnHealth" onclick="testHealth()">Check Health</button>
        <div id="resHealth" class="response-area">// Click above to test endpoint</div>
      </div>

      <!-- Quick Stateless OTP -->
      <div class="card">
        <h2><span>Stateless OTP</span> <span class="method get">GET /api/otp/generate-simple</span></h2>
        <div class="form-group">
          <label>Digits (4 - 10)</label>
          <input type="number" id="simpleDigits" value="6" min="4" max="10">
        </div>
        <div class="form-group">
          <label>Character Type</label>
          <select id="simpleType">
            <option value="numeric">Numeric (0-9)</option>
            <option value="alphanumeric">Alphanumeric (A-Z, 0-9)</option>
            <option value="alpha">Alpha Only (A-Z)</option>
          </select>
        </div>
        <button id="btnSimple" onclick="testSimpleOTP()">Generate Instant OTP</button>
        <div id="resSimple" class="response-area">// Click above to test endpoint</div>
      </div>

      <!-- Stateful OTP Generation -->
      <div class="card">
        <h2><span>Stateful OTP</span> <span class="method post">POST /api/otp/generate</span></h2>
        <div class="form-group">
          <label>Recipient / Identifier (Email or Phone)</label>
          <input type="text" id="statefulIdentifier" value="student@university.edu">
        </div>
        <div class="form-group">
          <label>Expiry (Seconds)</label>
          <input type="number" id="statefulExpiry" value="300">
        </div>
        <button id="btnGenerate" onclick="testStatefulGenerate()">Generate & Store OTP</button>
        <div id="resGenerate" class="response-area">// Generated OTP & reference_id will appear here</div>
      </div>

      <!-- OTP Verification -->
      <div class="card">
        <h2><span>Verify OTP</span> <span class="method post">POST /api/otp/verify</span></h2>
        <div class="form-group">
          <label>Reference ID</label>
          <input type="text" id="verifyRefId" placeholder="ref_xxxxxxxx">
        </div>
        <div class="form-group">
          <label>Supplied OTP Code</label>
          <input type="text" id="verifyCode" placeholder="Enter OTP">
        </div>
        <button id="btnVerify" onclick="testVerifyOTP()">Verify OTP</button>
        <div id="resVerify" class="response-area">// Verification result will appear here</div>
      </div>
    </div>

    <footer>
      QuickOTP Microservice • Built with Flask 3 & Python 3.13 • Ready for peer integration
    </footer>
  </div>

  <script>
    async function testHealth() {
      const box = document.getElementById('resHealth');
      box.textContent = "Connecting...";
      try {
        const res = await fetch('/api/health');
        const data = await res.json();
        box.innerHTML = `<span class="status-badge status-${res.status}">HTTP ${res.status} ${res.statusText}</span>` + JSON.stringify(data, null, 2);
      } catch (err) {
        box.innerHTML = `<span class="status-badge status-400">Network Error</span>` + err.message;
      }
    }

    async function testSimpleOTP() {
      const box = document.getElementById('resSimple');
      const digits = document.getElementById('simpleDigits').value;
      const type = document.getElementById('simpleType').value;
      box.textContent = "Requesting...";
      try {
        const res = await fetch(`/api/otp/generate-simple?digits=${digits}&type=${type}`);
        const data = await res.json();
        box.innerHTML = `<span class="status-badge status-${res.status}">HTTP ${res.status}</span>` + JSON.stringify(data, null, 2);
      } catch (err) {
        box.innerHTML = `<span class="status-badge status-400">Error</span>` + err.message;
      }
    }

    async function testStatefulGenerate() {
      const box = document.getElementById('resGenerate');
      const identifier = document.getElementById('statefulIdentifier').value;
      const expiry = parseInt(document.getElementById('statefulExpiry').value);
      box.textContent = "Generating...";
      try {
        const res = await fetch('/api/otp/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier, digits: 6, expiry_seconds: expiry, type: 'numeric' })
        });
        const data = await res.json();
        box.innerHTML = `<span class="status-badge status-${res.status}">HTTP ${res.status}</span>` + JSON.stringify(data, null, 2);
        if (data.reference_id) {
          document.getElementById('verifyRefId').value = data.reference_id;
          document.getElementById('verifyCode').value = data.otp || '';
        }
      } catch (err) {
        box.innerHTML = `<span class="status-badge status-400">Error</span>` + err.message;
      }
    }

    async function testVerifyOTP() {
      const box = document.getElementById('resVerify');
      const reference_id = document.getElementById('verifyRefId').value;
      const otp = document.getElementById('verifyCode').value;
      box.textContent = "Verifying...";
      try {
        const res = await fetch('/api/otp/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reference_id, otp })
        });
        const data = await res.json();
        box.innerHTML = `<span class="status-badge status-${res.status}">HTTP ${res.status}</span>` + JSON.stringify(data, null, 2);
      } catch (err) {
        box.innerHTML = `<span class="status-badge status-400">Error</span>` + err.message;
      }
    }
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" [QuickOTP Microservice] Starting on http://127.0.0.1:" + str(port))
    print(" Accessible endpoints:")
    print(f"  - GET  http://127.0.0.1:{port}/              (Web UI / Explorer)")
    print(f"  - GET  http://127.0.0.1:{port}/api/health    (Health Check)")
    print(f"  - GET  http://127.0.0.1:{port}/api/otp/generate-simple?digits=6&type=numeric")
    print(f"  - POST http://127.0.0.1:{port}/api/otp/generate (JSON body: identifier, digits, expiry_seconds)")
    print(f"  - POST http://127.0.0.1:{port}/api/otp/verify   (JSON body: reference_id, otp)")
    print("=" * 60)
    app.run(host="127.0.0.1", port=port, debug=False)
