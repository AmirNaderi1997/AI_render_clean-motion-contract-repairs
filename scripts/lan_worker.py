"""Explicitly start a private, restricted FFmpeg companion (not the cloud server)."""
import argparse
import ipaddress
import secrets
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from app.lan_worker import create_worker

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=5188)
    parser.add_argument('--root',type=Path,default=Path.home()/'.editorgpt-worker')
    parser.add_argument('--cert'); parser.add_argument('--key')
    parser.add_argument('--origin',action='append',default=[]); parser.add_argument('--allowed-host',action='append',default=[])
    args=parser.parse_args()
    address=ipaddress.ip_address(args.host)
    if not (address.is_private or address.is_loopback or args.host=='0.0.0.0'): parser.error('Public worker binding is not supported')
    if not address.is_loopback and not (args.cert and args.key and args.allowed_host): parser.error('LAN binding requires a trusted TLS certificate/key and --allowed-host (the private IP or trusted hostname)')
    code=secrets.token_urlsafe(24)
    print('EditorGPT pairing code (valid 5 minutes):',code,flush=True)
    app=create_worker(args.root,code,args.origin or ['http://localhost:5187','http://127.0.0.1:5187'],args.allowed_host or ['localhost','127.0.0.1'])
    uvicorn.run(app,host=args.host,port=args.port,ssl_certfile=args.cert,ssl_keyfile=args.key)
