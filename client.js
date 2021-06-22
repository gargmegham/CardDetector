// get DOM elements
var dataChannelLog = document.getElementById('data-channel');
var dataChannelStatus = document.getElementById('data-channel-status');

// peer connection
var pc = null;

// last response
var last_resp = "None"
var same_flag = false

// data channel
var dc = null, dcInterval = null;

function createPeerConnection() {
    var config = {
        sdpSemantics: 'unified-plan'
    };
    pc = new RTCPeerConnection(config);
    // connect video
    pc.addEventListener('track', function(evt) {
        if (evt.track.kind == 'video')
            document.getElementById('video').srcObject = evt.streams[0];
    });
    return pc;
}

function negotiate() {
    return pc.createOffer().then(function(offer) {
        return pc.setLocalDescription(offer);
    }).then(function() {
        // wait for ICE gathering to complete
        return new Promise(function(resolve) {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function() {
        var offer = pc.localDescription;
        codec = "default";
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
                video_transform: "none"
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then(function(response) {
        return response.json();
    }).then(function(answer) {
        return pc.setRemoteDescription(answer);
    }).catch(function(e) {
        alert(e);
    });
}

function start() {
    document.getElementById('start').style.display = 'none';
    var time_start = null;
    function current_stamp() {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    }
    pc = createPeerConnection();
    
    var parameters = {"ordered": true};
    dc = pc.createDataChannel('chat', parameters);
    dc.onclose = function() {
        clearInterval(dcInterval);
        dataChannelStatus.textContent = 'webcam closed\n';
    };
    dc.onopen = function() {
        dataChannelStatus.textContent = 'webcam is now open:\n';
        dcInterval = setInterval(function() {
            var message = 'give_me_cards ' + current_stamp();
            dc.send(message);
        }, 1000);
    };
    dc.onmessage = function(evt) {
        console.log(typeof evt.data, evt.data)
        if(typeof evt.data == "string" && (evt.data).startsWith('Ids:') && last_resp!=evt.data){
            dataChannelLog.textContent += '>>' + evt.data + '\n';
            last_resp = evt.data
            same_flag = false
            if(dataChannelLog.offsetHeight > 500){
                dataChannelLog.textContent = '>>' + evt.data + '\n';
            }
        }
        else if(typeof evt.data == "string" && !(evt.data).startsWith('Ids:') && !same_flag){
            var img = new Image();
            img.src = "data:image/png;base64,"+ evt.data;
            document.getElementById('cards').appendChild(img);
        }
        else if(typeof evt.data == "string" && (evt.data).startsWith('Ids:') && last_resp==evt.data){
            same_flag=true
        }
    };

    var constraints = {
        video: true
    };
    var resolution = "500x500";
    if (resolution) {
        resolution = resolution.split('x');
        constraints.video = {
            width: parseInt(resolution[0], 0),
            height: parseInt(resolution[1], 0)
        };
    } else {
        constraints.video = true;
    }

    if (constraints.video) {
        if (constraints.video) {
            document.getElementById('media').style.display = 'block';
            document.getElementById('detected_cards').style.display = 'block';
            document.getElementById('cards').style.display = 'block';
        }
        navigator.mediaDevices.getUserMedia(constraints).then(function(stream) {
            stream.getTracks().forEach(function(track) {
                pc.addTrack(track, stream);
            });
            return negotiate();
        }, function(err) {
            alert('Could not acquire media: ' + err);
        });
    } else {
        negotiate();
    }

    document.getElementById('stop').style.display = 'inline-block';
}

function stop() {
    document.getElementById('start').style.display = 'block';
    document.getElementById('stop').style.display = 'none';
    document.getElementById('media').style.display = 'none';
    // close data channel
    if (dc) {
        dc.close();
    }
    // close transceivers
    if (pc.getTransceivers) {
        pc.getTransceivers().forEach(function(transceiver) {
            if (transceiver.stop) {
                transceiver.stop();
            }
        });
    }
    // close local video
    pc.getSenders().forEach(function(sender) {
        sender.track.stop();
    });
    // close peer connection
    setTimeout(function() {
        pc.close();
    }, 500);
}