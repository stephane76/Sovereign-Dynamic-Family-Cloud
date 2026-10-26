#!/usr/bin/env python3
"""DFC admission tests; no secret or auth_key is printed."""
import argparse, base64, sys
import httpx
from cryptography.hazmat.primitives import serialization
p = argparse.ArgumentParser()
p.add_argument('--endpoint', required=True)
p.add_argument('--id', required=True)
p.add_argument('--private-key', required=True)
p.add_argument('--scenario', choices=['ok','unknown','bad-signature','replay'], required=True)
a = p.parse_args()
with open(a.private_key, 'rb') as fh:
    priv=serialization.load_pem_private_key(fh.read(), password=None)
try:
    with httpx.Client(timeout=20) as c:
        device_id = 'dfc-unknown-device-999' if a.scenario == 'unknown' else a.id
        r=c.post(a.endpoint+'/v1/challenge', json={'device_id':device_id})
        if a.scenario=='unknown':
            valid=r.status_code==403
            print('unknown:',r.status_code,'PASS' if valid else 'FAIL')
        else:
            r.raise_for_status()
            nonce=r.json()['nonce']
            payload=f'dfc-admission-v1\n{device_id}\n{nonce}\n'.encode()
            if a.scenario=='bad-signature':
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                priv=Ed25519PrivateKey.generate()
            signature=base64.b64encode(priv.sign(payload)).decode()
            data={'device_id':device_id,'nonce':nonce,'signature':signature}
            first=c.post(a.endpoint+'/v1/admit',json=data)
            if a.scenario=='ok':
                valid=first.status_code==200 and bool(first.json().get('auth_key'))
                print('ok:',first.status_code,'PASS' if valid else 'FAIL')
            elif a.scenario=='bad-signature':
                valid=first.status_code==403
                print('bad-signature:',first.status_code,'PASS' if valid else 'FAIL')
            else:
                second=c.post(a.endpoint+'/v1/admit',json=data)
                valid=first.status_code==200 and second.status_code==403
                print('replay:',first.status_code,second.status_code,'PASS' if valid else 'FAIL')
except (httpx.HTTPError, ValueError, KeyError) as e:
    print('FAIL:',type(e).__name__,file=sys.stderr)
    sys.exit(1)
sys.exit(0 if valid else 1)
