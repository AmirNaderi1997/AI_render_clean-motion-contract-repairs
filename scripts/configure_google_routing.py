"""Verify native Google, then activate bounded light-task routes; no quota reads."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from brain import lm_gateway as gateway
from app import lm_store as store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--activate",action="store_true")
    args=parser.parse_args()
    gateway.register_task_models()
    candidates=["google:gemini-3.5-flash", "custom:DeepSeek-V4-Flash#arvancloud-all-models",
                "custom:CLAUDE_SONNET_5_5#jarvis-all-models"]
    verified=[]
    for mid in candidates:
        try:
            gateway.probe_model(mid,"chat")
            # Independently verify JSON content without requiring native schema features.
            result,_=gateway.complete("general_chat",[{"role":"user","content":'Return only {"ok":true}.'}],
                                      model_override=mid,probe=True,tokens=256)
            if json.loads(gateway.adapters.text("chat",result)) != {"ok":True}:
                raise ValueError("JSON semantic check failed")
            verified.append(mid)
            print(json.dumps({"model":mid,"status":"verified"}),flush=True)
        except Exception as exc:
            print(json.dumps({"model":mid,"status":"failed","error":gateway.safe(str(exc),300)}),flush=True)
    if not verified or verified[0]!=candidates[0]:
        raise SystemExit("Google is not verified; existing routes left unchanged")
    if args.activate:
        routes=gateway.defaults()
        keys=("general_chat","intent_classification","segment_analysis","transcript_correction","subtitle_formatting")
        previous={key:routes[key] for key in keys}
        store.save("settings",{"before_google_routing":previous})
        changes={key:{**routes[key],"models":verified,"endpoint":"chat","enabled":True,
                     "automatic_fallback":True,"max_retries":0,"temperature":None,"streaming":False}
                 for key in keys}
        store.save("routes",changes)
        print("Activated Google-first routes; Vercel excluded; quota preflight disabled")


if __name__=="__main__":main()
