import React from "react";
import {registerRoot} from "remotion";
import {EditorGPTVideo} from "./video.jsx";
import {DirectedVideo} from "./DirectedVideo.jsx";

registerRoot(() => <><EditorGPTVideo/><DirectedVideo/></>);
