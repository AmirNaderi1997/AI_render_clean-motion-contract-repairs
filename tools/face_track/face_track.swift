// Print the largest face in each image as JSON lines, using Apple's Vision
// framework (no model download). Usage: face_track <image>...
// Output per image: {"file": "...", "face": [cx, cy, w, h] | null} with
// coordinates normalised to the image, origin top-left.
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    var face: [Double]? = nil
    if let image = NSImage(contentsOfFile: path),
       let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        let request = VNDetectFaceRectanglesRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([request])
        if let best = (request.results ?? []).max(by: { $0.boundingBox.width * $0.boundingBox.height
                                                         < $1.boundingBox.width * $1.boundingBox.height }) {
            let b = best.boundingBox
            face = [Double(b.midX), Double(1 - b.midY), Double(b.width), Double(b.height)]
        }
    }
    let payload: [String: Any] = ["file": path, "face": face as Any? ?? NSNull()]
    if let data = try? JSONSerialization.data(withJSONObject: payload),
       let line = String(data: data, encoding: .utf8) {
        print(line)
    }
}
