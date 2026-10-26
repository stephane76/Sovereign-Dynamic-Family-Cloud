#!/usr/bin/env python3
"""Test Box client (requires private Ed25519 PEM generated OFF the VPS)."""
import argparse
import base64
import httpx
from cryptography.hazmat.primitives import serialization
p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--id',required=True);p.add_argument('--private-key',required=True);a=p.parse_args()
with open(a.private_key,'rb') as f: private=serialization.load_pem_private_key(f.read(),password=None)
with httpx.Client(timeout=15) as client:
 ch=client.post(a.endpoint+'/v1/challenge',json={'device_id':a.id});ch.raise_for_status();nonce=ch.json()['nonce']
 payload=f'dfc-admission-v1\n{a.id}\n{nonce}\n'.encode()
 signature=base64.b64encode(private.sign(payload)).decode()
 resp=client.post(a.endpoint+'/v1/admit',json={'device_id':a.id,'nonce':nonce,'signature':signature});resp.raise_for_status()
 print('Admission accepted. Use auth_key privately on the Box; DO NOT print key in logs.')
 # Client integration must consume resp.json()['auth_key'] immediately via tailscale up.
