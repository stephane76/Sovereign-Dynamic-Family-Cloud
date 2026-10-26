#!/usr/bin/env python3
"""Simulated Box enrollment; the auth_key stays in memory and is passed via stdin."""
import argparse, base64, subprocess, sys
import httpx
from cryptography.hazmat.primitives import serialization
p=argparse.ArgumentParser()
p.add_argument('--endpoint',required=True)
p.add_argument('--id',required=True)
p.add_argument('--private-key',required=True)
p.add_argument('--container',default='dfc-box-test')
p.add_argument('--login-server',required=True)
a=p.parse_args()
with open(a.private_key,'rb') as f:
    private=serialization.load_pem_private_key(f.read(),password=None)
try:
    with httpx.Client(timeout=20) as client:
        ch=client.post(a.endpoint+'/v1/challenge',json={'device_id':a.id});ch.raise_for_status()
        nonce=ch.json()['nonce']
        payload=f'dfc-admission-v1\n{a.id}\n{nonce}\n'.encode()
        signature=base64.b64encode(private.sign(payload)).decode()
        resp=client.post(a.endpoint+'/v1/admit',json={'device_id':a.id,'nonce':nonce,'signature':signature});resp.raise_for_status()
        key=resp.json()['auth_key']
    print('Ed25519 admission: PASS')
    result=subprocess.run(['sudo','docker','exec','-i',a.container,'tailscale','up',
        '--login-server='+a.login_server,'--hostname='+a.id,'--accept-dns=false',
        '--auth-key=file:/dev/stdin'],input=key+'\n',text=True,stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,timeout=90)
    print('Tailscale enrollment:', 'PASS' if result.returncode==0 else 'FAIL')
    if result.returncode != 0:
        print('Check the tailscaled logs and HTTPS connectivity; never publish secrets.',file=sys.stderr)
    sys.exit(result.returncode)
except (httpx.HTTPError,KeyError,ValueError,OSError,subprocess.TimeoutExpired) as e:
    print('FAIL:',type(e).__name__,file=sys.stderr)
    sys.exit(1)
