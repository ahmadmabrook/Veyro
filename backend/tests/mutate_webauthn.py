"""Break each WebAuthn check on purpose and require its own case to fail.

A verifier that accepted the signature it generated and refused nothing else would pass the
acceptance tests; these are what say the refusals bite. Every mutation is one line.
"""
import pathlib
import subprocess
import sys

SRC = pathlib.Path("app/identity/webauthn.py")
MUTATIONS = [
    ("type check removed", '    if client.type != "webauthn.get":',
     '    if False:'),
    ("challenge compared by length",
     "    if not hmac.compare_digest(client.challenge, expected_challenge):",
     "    if len(client.challenge) != len(expected_challenge):"),
    ("origin allow-list widened to a suffix", "    if client.origin not in allowed_origins:",
     "    if not any(client.origin.endswith(o.split('//')[-1]) for o in allowed_origins):"),
    ("cross-origin accepted", "    if client.cross_origin:", "    if False:"),
    ("rp id hash unchecked", "    if not hmac.compare_digest(auth.rp_id_hash, rp_id_hash(rp_id)):",
     "    if False:"),
    ("user-present ignored", "    if not auth.user_present:", "    if False:"),
    ("user-verification ignored", "    if require_user_verification and not auth.user_verified:",
     "    if False:"),
    ("signature not verified", "    verify_signature(public_key=key, algorithm=algorithm,",
     "    _ = key; _unused = ("),
    ("short authenticator data sliced", "    if len(raw) < _MINIMUM_AUTH_DATA:", "    if False:"),
    ("factor from BS rather than BE",
     '    return "passkey_synced" if backup_eligible else "passkey_hardware"',
     '    return "passkey_hardware"'),
    ("algorithm not matched to the key",
     "    if algorithm == ES256:\n        if not isinstance(key, ec.EllipticCurvePublicKey)"
     " or not isinstance(",
     "    if False:\n        if not isinstance(key, ec.EllipticCurvePublicKey)"
     " or not isinstance("),
    ("lenient base64url", '    if value.strip("=") != value or any(c in value for c in "+/"):',
     "    if False:"),
]

original = SRC.read_text()
caught, gaps, notrun = 0, [], []
for name, frm, to in MUTATIONS:
    if original.count(frm) != 1:
        notrun.append(f"{name}: anchor appears {original.count(frm)} times, not once")
        print(f"SKIP  {name}")
        continue
    SRC.write_text(original.replace(frm, to, 1))
    try:
        run = subprocess.run([sys.executable, "-m", "unittest", "tests.test_webauthn"],
                             capture_output=True, text=True, timeout=300)
        out = run.stdout + run.stderr
        if "Ran 0 tests" in out or "Error" in out.split("\n")[0]:
            notrun.append(f"{name}: the suite did not run")
            print(f"SKIP  {name} (suite did not run)")
        elif run.returncode != 0:
            caught += 1
            print(f"ok    {name} -- caught")
        else:
            gaps.append(name)
            print(f"GAP   {name} -- the suite stayed green")
    finally:
        SRC.write_text(original)

print(f"\n{caught}/{len(MUTATIONS)} caught")
if gaps:
    print("UNCAUGHT:\n  " + "\n  ".join(gaps))
if notrun:
    print("NOT RUN:\n  " + "\n  ".join(notrun))
sys.exit(0 if not gaps and not notrun else 1)
