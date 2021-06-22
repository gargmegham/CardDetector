import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid
from BusinessLogic import card_detection as CardDetection
from aiohttp import web
from av import VideoFrame
import base64
from PIL import Image
from io import BytesIO
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()

cards_in_frame = None

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track, transform):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform
        self.detected_cards = None
        self.card_dict = dict()
        self.phash_cnt = dict()
        self.current_cards = list()

    async def recv(self):
        global cards_in_frame
        frame = await self.track.recv()
        # rotate image
        img = frame.to_ndarray(format="bgr24")
        img, self.detected_cards, self.card_dict, self.phash_cnt, self.current_cards, cards_in_frame = CardDetection.detect_image(img, 
            self.card_dict,
            self.phash_cnt,
            self.current_cards)
        json.dump(self.card_dict, open("card_dict.json", "w"))
        # rebuild a VideoFrame, preserving timing information
        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    recorder = MediaBlackhole()

    @pc.on("datachannel")
    def on_datachannel(channel):
        global cards_in_frame
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("give_me_cards") and len(cards_in_frame) > 0:
                img = Image.fromarray(list(cards_in_frame.values())[-1]) # convert each frame to an image
                output_buffer = BytesIO() #Create a BytesIO
                img.save(output_buffer, format='JPEG') #write output_buffer
                byte_data = output_buffer.getvalue() #Read in memory
                base64_data = base64.b64encode(byte_data) # BASE64
                base64_data = str(base64_data)
                base64_data = base64_data[2:-1]
                resp = "Ids: " + ", ".join(list(cards_in_frame.keys()))
                channel.send(resp)
                channel.send(str(base64_data))

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE connection state is %s", pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)
        
        local_video = VideoTransformTrack(
            track, transform=params["video_transform"]
        )
        pc.addTrack(local_video)

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC Card detector")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server (default: 8080)")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
