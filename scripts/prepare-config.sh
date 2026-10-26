#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 - "$@" <<'PY'
import ipaddress, os, pathlib, re, sys, tempfile
from urllib.parse import urlsplit
P=pathlib.Path
if len(sys.argv)>2 or (len(sys.argv)==2 and sys.argv[1]!='--force'):
    sys.exit('Usage: bash scripts/prepare-config.sh [--force]')
force=len(sys.argv)==2
p=P('.env')
if not p.is_file(): sys.exit('Missing root .env')
settings={}
for n,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
    line=line.strip()
    if not line or line.startswith('#'): continue
    match=re.fullmatch(r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
    if not match: sys.exit(f'Invalid root .env line {n}')
    k,v=match.groups()
    if len(v)>1 and v[0]==v[-1] and v[0] in '\'"': v=v[1:-1]
    settings[k]=v
required=['DOMAIN','ACME_EMAIL','PUBLIC_IP','ACME_CA_SERVER','ACME_EAB_KID','ACME_EAB_HMAC']
missing=[k for k in required if not settings.get(k)]
if missing: sys.exit('Missing .env variables: '+', '.join(missing))
domain=settings['DOMAIN'].strip().lower().rstrip('.')
email=settings['ACME_EMAIL'].strip()
ip=settings['PUBLIC_IP'].strip()
ca=settings['ACME_CA_SERVER'].strip()
kid=settings['ACME_EAB_KID'].strip()
hmac=settings['ACME_EAB_HMAC'].strip()
if not re.fullmatch(r'(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',domain): sys.exit('DOMAIN invalid')
if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): sys.exit('ACME_EMAIL invalid')
try:
    if not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).version!=4: raise ValueError()
except ValueError: sys.exit('PUBLIC_IP invalid')
u=urlsplit(ca)
if u.scheme!='https' or not u.netloc or u.username or u.password or u.fragment or any(x in ca for x in '\n\r\t #"\''):
    sys.exit('ACME_CA_SERVER must be an HTTPS directory URL')
if not re.fullmatch(r'[A-Za-z0-9_-]+',kid): sys.exit('ACME_EAB_KID has unexpected characters')
if not re.fullmatch(r'[A-Za-z0-9_-]+',hmac): sys.exit('ACME_EAB_HMAC must be base64url without padding')
# Secrets are intentionally written only to ignored, mode-0600 *active* Traefik YAML.
# Git-tracked examples contain PLACEHOLDER markers, never secrets.
pairs={
'configs/headscale/config.yaml.example':'configs/headscale/config.yaml',
'configs/headscale/policy.hujson.example':'configs/headscale/policy.hujson',
'configs/traefik/traefik.yml.example':'configs/traefik/traefik.yml',
'configs/traefik/dynamic.example/headscale.yml.example':'configs/traefik/dynamic/headscale.yml',
'configs/traefik/dynamic.example/admission.yml.example':'configs/traefik/dynamic/admission.yml',
'admission/.env.example':'admission/.env'}
rendered={}
for src,dst in pairs.items():
    if not P(src).is_file(): sys.exit('Missing example '+src)
    s=P(src).read_text(encoding='utf8').replace('admin@yourfamily.eu',email).replace('yourfamily.eu',domain).replace('REPLACE_WITH_VPS_IPV4',ip)
    if dst=='configs/traefik/traefik.yml':
        for marker,val in [('ACME_CA_SERVER_PLACEHOLDER',ca),('ACME_EAB_KID_PLACEHOLDER',kid),('ACME_EAB_HMAC_PLACEHOLDER',hmac)]:
            if marker not in s: sys.exit('Missing marker in Traefik template: '+marker)
            s=s.replace(marker,val)
        if 'certificatesResolvers:\n  actalis:' not in s: sys.exit('Actalis resolver missing')
    if dst=='admission/.env':
        s='\n'.join(l for l in s.splitlines() if not l.startswith('HEADSCALE_USER_ID='))+'\n'
        if 'PUBLIC_HEADSCALE_URL=' not in s: sys.exit('Admission PUBLIC_HEADSCALE_URL missing')
    if any(x in s for x in ['yourfamily.eu','REPLACE_WITH_VPS_IPV4']) or (dst=='configs/traefik/traefik.yml' and '_PLACEHOLDER' in s):
        sys.exit('Unresolved placeholder in '+src)
    rendered[dst]=s
for dst,s in rendered.items():
    path=P(dst)
    if path.exists() and not force:
        print('Kept:',dst);continue
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.dfc-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf8',newline='\n') as f:f.write(s)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    print('Generated:',dst)
print('Done. Private Traefik config contains EAB credentials; never commit it.')
PY
