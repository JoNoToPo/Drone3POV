"""Check the bridge's live video from a laptop.

Connects to GET /v1/video, decodes the raw H.264 with PyAV (FFmpeg), and reports the resolution,
frame rate and how long the first frame took. Optionally saves a frame so you can see the image.

    pip install av pillow
    python bridge/tools/check_video.py http://192.168.1.42:8765
    python bridge/tools/check_video.py http://192.168.1.42:8765 --feed transcoded --save frame.jpg

If the primary feed connects but never decodes a frame, try --feed transcoded: some DJI drones send
video that standard decoders can't read, and the SDK's transcoded feed is plain H.264.
"""

import argparse
import sys
import time

import av


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bridge", help="bridge URL from the phone screen, e.g. http://192.168.1.42:8765")
    parser.add_argument("--feed", choices=("primary", "transcoded"), default="primary")
    parser.add_argument("--seconds", type=float, default=10.0, help="how long to watch (default 10)")
    parser.add_argument("--save", metavar="FILE", help="save one decoded frame as an image, e.g. frame.jpg")
    args = parser.parse_args()

    url = f"{args.bridge.rstrip('/')}/v1/video?feed={args.feed}"
    print(f"Connecting to {url}")
    started = time.perf_counter()
    try:
        # Low-delay options: don't buffer ahead, show frames as soon as they decode.
        container = av.open(
            url,
            format="h264",
            options={"fflags": "nobuffer", "flags": "low_delay", "probesize": "32768"},
            timeout=(5.0, 5.0),
        )
    except av.error.HTTPError as exc:
        print(f"The bridge refused the stream (no drone connected, or too many viewers): {exc}", file=sys.stderr)
        return 1
    except av.error.FFmpegError as exc:
        # Connection refused, wrong address, or no video within the timeout all land here.
        print(f"Couldn't connect, or no video arrived in 5 s. Check the URL on the phone screen. ({exc})", file=sys.stderr)
        return 1

    frames = 0
    first_frame_s = None
    size = None
    saved = False
    deadline = started + args.seconds
    try:
        for frame in container.decode(video=0):
            frames += 1
            if first_frame_s is None:
                first_frame_s = time.perf_counter() - started
                size = (frame.width, frame.height)
                print(f"First frame after {first_frame_s:.2f} s: {frame.width}x{frame.height}")
            if args.save and not saved:
                frame.to_image().save(args.save)
                saved = True
                print(f"Saved a frame to {args.save}")
            if time.perf_counter() >= deadline:
                break
    except av.error.EOFError:
        print("The bridge ended the stream (drone disconnected, or this viewer fell behind).")
    except (av.error.OSError, av.error.TimeoutError) as exc:
        print(f"Stream stopped: {exc}")
    finally:
        container.close()

    if frames == 0:
        print("No frames decoded.", file=sys.stderr)
        if args.feed == "primary":
            print("Try --feed transcoded.", file=sys.stderr)
        return 1

    watched = time.perf_counter() - started - (first_frame_s or 0)
    fps = (frames - 1) / watched if watched > 0 and frames > 1 else 0.0
    print(f"Decoded {frames} frames at {size[0]}x{size[1]}, about {fps:.1f} fps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
