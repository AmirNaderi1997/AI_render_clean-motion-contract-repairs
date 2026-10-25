import React from "react";
import {Reel} from "@editor-reel";
import {Audio} from "@remotion/media";

// Functions/components belong to the renderer, not serializable AI input props.
export function BrowserReel(props:Record<string,unknown>) {
  return <Reel {...props} resolveAsset={(url:string)=>url} AudioComponent={Audio}/>;
}
