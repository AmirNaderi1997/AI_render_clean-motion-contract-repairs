"""Install a supplied credential into a private, Git/Docker-ignored file. Never print it."""
from pathlib import Path
import argparse
import re
import subprocess
import os


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--admin-user-id", default="")
    args=parser.parse_args()
    if args.source.suffix.lower()==".rtf":
        text=subprocess.check_output(["textutil","-convert","txt","-stdout",str(args.source)],text=True).strip()
    else: text=args.source.read_text().strip()
    match=re.search(r"(?:freellmapi-|sk-)[A-Za-z0-9_.-]+",text)
    key=match.group(0) if match else text.split("=",1)[-1].strip().strip("\"'")
    if len(key)<16 or any(c.isspace() for c in key): raise ValueError("Invalid credential file")
    target=Path(__file__).resolve().parents[1]/".lmapi_key"
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w") as stream: stream.write(key)
    target.chmod(0o600)
    if args.admin_user_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",args.admin_user_id): raise ValueError("Invalid administrator ID")
        env=target.parent/".env"
        lines=env.read_text().splitlines() if env.exists() else []
        current=next((line.split("=",1)[1].strip().strip("\"'") for line in lines if line.startswith("AI_ADMIN_USER_IDS=")),"")
        ids={v.strip() for v in current.split(",") if v.strip()};ids.add(args.admin_user_id)
        lines=[line for line in lines if not line.startswith("AI_ADMIN_USER_IDS=")]
        lines.append("AI_ADMIN_USER_IDS="+",".join(sorted(ids)))
        env.write_text("\n".join(lines)+"\n");env.chmod(0o600)
    print("LM credential installed privately; value omitted.")


if __name__=="__main__": main()
