"""Bounded gateway setup. Does not generate paid media or re-render user jobs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from brain import lm_gateway as gateway
from app import lm_store as store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--probe",action="store_true",help="Run six small capability probes against the catalog's auto router")
    parser.add_argument("--activate",action="store_true",help="Use already-verified auto routes")
    args=parser.parse_args()
    print(json.dumps(gateway.sync_models()))
    if args.probe:
        for capability in ("chat","responses","messages","embeddings","vision","streaming"):
            try:
                row=gateway.probe_model("auto",capability)
                print(json.dumps({"capability":capability,"status":"passed","latency_ms":row.get("test_latency_ms")}),flush=True)
            except Exception as exc:
                print(json.dumps({"capability":capability,"status":"failed","message":gateway.safe(str(exc),300)}),flush=True)
    if args.activate:
        model=store.records("models").get("auto",{})
        routes=gateway.defaults(); changed={}
        for key,row in routes.items():
            if key in {"general_chat","editing_agent","subtitles","script"} and "chat" in gateway.capabilities(model):
                row.update(models=["auto"],endpoint="chat",enabled=True)
                if key=="general_chat" and "streaming" in gateway.capabilities(model): row["streaming"]=True
                changed[key]=row
            if key=="video_understanding" and {"chat","vision"}.issubset(gateway.capabilities(model)):
                row.update(models=["auto"],endpoint="chat",enabled=True);changed[key]=row
        if changed:store.save("routes",changed)
        print("Activated verified text/vision routes; specialized engines unchanged.")


if __name__=="__main__":main()
