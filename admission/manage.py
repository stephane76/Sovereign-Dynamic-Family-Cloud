#!/usr/bin/env python3
"""Offline operator provisioning: run on VPS, NEVER expose as an HTTP endpoint."""
import argparse
import os
import sqlite3
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('action',choices=['register','revoke','list'])
p.add_argument('--id')
p.add_argument('--pubkey',help='32-byte Ed25519 public key, hex encoded')
p.add_argument('--site',choices=['be','es'])
p.add_argument('--role',choices=['gateway','storage','compute'])
a=p.parse_args()
if a.action!='list' and not a.id: p.error('--id required')
db=sqlite3.connect(os.environ.get('ADMISSION_DB','/var/lib/dfc-admission/registry.sqlite3'))
if a.action=='register':
 if not a.pubkey or not a.site or not a.role: p.error('register needs --pubkey --site --role')
 if len(bytes.fromhex(a.pubkey))!=32: p.error('invalid Ed25519 key size')
 db.execute('INSERT INTO devices(device_id,public_key,site,role,status) VALUES(?,?,?,?,?)',(a.id,a.pubkey,a.site,a.role,'allowed'))
elif a.action=='revoke':
 n=db.execute("UPDATE devices SET status='revoked' WHERE device_id=?",(a.id,)).rowcount
 db.execute("DELETE FROM challenges WHERE device_id=?",(a.id,))
 if not n: p.error('unknown device')
 print('Admission revoked. IMPORTANT: expire existing Headscale node separately; local revoke does not disconnect an enrolled node.')
else:
 for row in db.execute('SELECT device_id,site,role,status FROM devices ORDER BY device_id'): print(*row)
db.commit()
