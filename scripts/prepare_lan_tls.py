"""Generate a private app-specific CA and short-lived LAN TLS certificate.

Does not install/trust anything in the OS. Share only ca.cer, never the keys.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ip',action='append',required=True)
    parser.add_argument('--name',action='append',default=[])
    args=parser.parse_args()
    for value in args.ip:
        address=ipaddress.ip_address(value)
        if not address.is_private or address.is_unspecified: parser.error('Only private LAN addresses are accepted')
    for name in args.name:
        if not name.endswith('.local') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in name): parser.error('Names must be .local hostnames')
    binary=shutil.which('openssl')
    if not binary: parser.error('OpenSSL is required')
    root=Path(__file__).resolve().parents[1]/'.local-lan'
    os.umask(0o077);root.mkdir(mode=0o700,exist_ok=True)
    def run(*command): subprocess.run([binary,*command],cwd=root,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not (root/'ca.pem').exists():
        run('genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out','ca-key.pem')
        run('req','-x509','-new','-key','ca-key.pem','-sha256','-days','365','-subj','/CN=EditorGPT Local LAN - This Mac',
            '-addext','basicConstraints=critical,CA:TRUE,pathlen:0','-addext','keyUsage=critical,keyCertSign,cRLSign','-out','ca.pem')
    run('genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out','server-key.pem')
    san=','.join(['DNS:localhost','IP:127.0.0.1']+['IP:'+x for x in args.ip]+['DNS:'+n for n in args.name])
    run('req','-new','-key','server-key.pem','-subj','/CN=EditorGPT LAN','-addext','subjectAltName='+san,
        '-addext','basicConstraints=critical,CA:FALSE','-addext','keyUsage=critical,digitalSignature,keyEncipherment','-addext','extendedKeyUsage=serverAuth','-out','server.csr')
    run('x509','-req','-in','server.csr','-CA','ca.pem','-CAkey','ca-key.pem','-CAcreateserial','-days','90','-sha256','-copy_extensions','copy','-out','server.pem')
    run('x509','-in','ca.pem','-outform','DER','-out','ca.cer')
    result=subprocess.run([binary,'x509','-in',str(root/'ca.pem'),'-noout','-fingerprint','-sha256'],capture_output=True,text=True,check=True)
    print('Private keys remain in',root)
    print('Share only the public ca.cer; trust installation on each phone/tablet is manual.')
    print(result.stdout.strip())
