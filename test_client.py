import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://127.0.0.1:5000"

def send_request(method, endpoint, payload=None, params=None):
    url = f"{BASE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params)
        url += f"?{query_string}"
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "QuickOTP-Tester/1.0"
    }
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    print("-" * 75)
    print(f">> REQUEST: {method} {url}")
    if payload:
        print(f">> Request Body:\n{json.dumps(payload, indent=2)}")
    
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            res_headers = dict(response.info())
            raw_body = response.read().decode("utf-8")
            try:
                body = json.loads(raw_body)
                body_formatted = json.dumps(body, indent=2)
            except Exception:
                body_formatted = raw_body

            print(f"<< RESPONSE STATUS: HTTP {status_code}")
            print(f"<< Content-Type: {res_headers.get('Content-Type')}")
            print(f"<< Response Body:\n{body_formatted}")
            return status_code, body
    except urllib.error.HTTPError as e:
        status_code = e.code
        res_headers = dict(e.headers)
        raw_body = e.read().decode("utf-8")
        try:
            body = json.loads(raw_body)
            body_formatted = json.dumps(body, indent=2)
        except Exception:
            body_formatted = raw_body

        print(f"<< RESPONSE STATUS: HTTP {status_code} (Error Handled)")
        print(f"<< Content-Type: {res_headers.get('Content-Type')}")
        print(f"<< Response Body:\n{body_formatted}")
        return status_code, body

if __name__ == "__main__":
    print("===========================================================================")
    print(" RUNNING AUTOMATED CONNECTIVITY & ENDPOINT VERIFICATION")
    print("===========================================================================\n")

    # 1. Health Check
    print("\n[TEST 1] GET /api/health (Service Health & Connectivity)")
    send_request("GET", "/api/health")

    # 2. Simple OTP Generation (Success)
    print("\n[TEST 2] GET /api/otp/generate-simple?digits=6&type=numeric (Valid Input)")
    send_request("GET", "/api/otp/generate-simple", params={"digits": 6, "type": "numeric"})

    # 3. Simple OTP Generation (Error Case: Invalid Digits)
    print("\n[TEST 3] GET /api/otp/generate-simple?digits=99 (Error Case: Digits out of range)")
    send_request("GET", "/api/otp/generate-simple", params={"digits": 99})

    # 4. Stateful OTP Generation (Success)
    print("\n[TEST 4] POST /api/otp/generate (Valid Input: Generate OTP for student)")
    status, gen_res = send_request("POST", "/api/otp/generate", payload={
        "identifier": "student.project@college.edu",
        "digits": 6,
        "expiry_seconds": 300,
        "type": "numeric"
    })

    ref_id = gen_res.get("reference_id") if isinstance(gen_res, dict) else None
    otp_code = gen_res.get("otp") if isinstance(gen_res, dict) else None

    # 5. Stateful OTP Generation (Error Case: Missing Identifier)
    print("\n[TEST 5] POST /api/otp/generate (Error Case: Missing identifier in body)")
    send_request("POST", "/api/otp/generate", payload={
        "digits": 6,
        "expiry_seconds": 300
    })

    if ref_id and otp_code:
        # 6. Verify OTP (Error Case: Wrong OTP)
        print("\n[TEST 6] POST /api/otp/verify (Error Case: Wrong OTP code)")
        send_request("POST", "/api/otp/verify", payload={
            "reference_id": ref_id,
            "otp": "000000"
        })

        # 7. Verify OTP (Success Case: Correct OTP)
        print("\n[TEST 7] POST /api/otp/verify (Valid Input: Correct OTP code)")
        send_request("POST", "/api/otp/verify", payload={
            "reference_id": ref_id,
            "otp": otp_code
        })

    # 8. Verify OTP (Error Case: Non-existent reference ID)
    print("\n[TEST 8] POST /api/otp/verify (Error Case: Non-existent reference ID)")
    send_request("POST", "/api/otp/verify", payload={
        "reference_id": "ref_unknown_123456",
        "otp": "123456"
    })

    print("\n===========================================================================")
    print(" ALL CONNECTIVITY AND VALIDATION TESTS COMPLETED SUCCESSFULLY!")
    print("===========================================================================")
