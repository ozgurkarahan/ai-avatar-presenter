import React, { useState, useRef, useEffect, useCallback } from 'react';
import { translateText, type Presentation } from '../services/api';

interface Props {
  presentation: Presentation;
  currentSlide: number;
  language: string;
}

const styles: Record<string, React.CSSProperties> = {
  container: { textAlign: 'center' as const },
  title: {
    fontSize: '14px',
    fontWeight: 600,
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  videoContainer: {
    width: '100%',
    aspectRatio: '16/9',
    background: '#1a1a2e',
    borderRadius: '10px',
    overflow: 'hidden',
    position: 'relative' as const,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  video: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
  },
  placeholder: {
    color: '#888',
    fontSize: '14px',
  },
  controls: {
    display: 'flex',
    gap: '8px',
    marginTop: '12px',
    justifyContent: 'center',
  },
  btn: {
    padding: '8px 18px',
    border: 'none',
    borderRadius: '6px',
    fontSize: '13px',
    cursor: 'pointer',
    fontWeight: 500,
  },
  btnPrimary: {
    background: '#005599',
    color: 'white',
  },
  btnDanger: {
    background: '#c0392b',
    color: 'white',
  },
  btnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  status: {
    marginTop: '8px',
    fontSize: '12px',
    color: '#666',
  },
};

export default function AvatarPanel({ presentation, currentSlide, language }: Props) {
  const [connected, setConnected] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [status, setStatus] = useState('Not connected');
  const videoRef = useRef<HTMLVideoElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);

  // Set up WebRTC peer connection with ICE servers from Azure
  const setupWebRTC = useCallback((iceServers: any, username?: string, credential?: string) => {
    let servers = Array.isArray(iceServers) ? iceServers : [{ urls: iceServers }];
    if (username && credential) {
      servers = servers.map((s: any) => ({
        urls: typeof s === 'string' ? s : s.urls,
        username,
        credential,
        credentialType: 'password' as const,
      }));
    }

    const pc = new RTCPeerConnection({
      iceServers: servers,
      bundlePolicy: 'max-bundle',
    });
    peerConnectionRef.current = pc;

    pc.oniceconnectionstatechange = () => {
      console.log('[WebRTC] ICE state:', pc.iceConnectionState);
    };

    // When ICE gathering is complete, send the SDP offer to backend
    pc.onicecandidate = (e) => {
      if (!e.candidate && pc.localDescription) {
        const sdp = btoa(JSON.stringify({ type: 'offer', sdp: pc.localDescription.sdp }));
        console.log('[WebRTC] ICE gathering complete, sending SDP offer');
        wsRef.current?.send(JSON.stringify({ type: 'session.avatar.connect', client_sdp: sdp }));
      }
    };

    // Receive video/audio tracks from avatar
    pc.ontrack = (e) => {
      console.log('[WebRTC] Got track:', e.track.kind);
      if (e.track.kind === 'video' && videoRef.current) {
        videoRef.current.srcObject = e.streams[0];
        videoRef.current.play().catch(() => {});
      } else if (e.track.kind === 'audio') {
        const audio = document.createElement('audio');
        audio.srcObject = e.streams[0];
        audio.autoplay = true;
        audio.style.display = 'none';
        document.body.appendChild(audio);
      }
    };

    // Add recv-only transceivers (we only receive avatar stream)
    pc.addTransceiver('video', { direction: 'recvonly' });
    pc.addTransceiver('audio', { direction: 'recvonly' });

    // Create and set local SDP offer
    pc.createOffer().then((offer) => {
      pc.setLocalDescription(offer);
    });
  }, []);

  // Handle SDP answer from Azure (via backend proxy)
  const handleAnswer = useCallback((msg: any) => {
    const pc = peerConnectionRef.current;
    if (!pc || pc.signalingState !== 'have-local-offer') return;

    const sdp = msg.server_sdp
      ? JSON.parse(atob(msg.server_sdp)).sdp
      : msg.sdp || msg.answer;

    if (sdp) {
      console.log('[WebRTC] Setting remote SDP answer');
      pc.setRemoteDescription({ type: 'answer', sdp });
    }
  }, []);

  // Handle incoming WebSocket messages from backend proxy
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data);
      console.log('[WS] Message:', msg.type || 'unknown', Object.keys(msg).join(','));

      if (msg.type === 'proxy.connected') {
        setStatus('Connected to Azure Voice API');
      } else if (msg.type === 'session.updated') {
        const session = msg.session || {};
        // Extract ICE servers (try multiple paths like voicelive)
        const servers = session?.avatar?.ice_servers || session?.rtc?.ice_servers || session?.ice_servers;
        const username = session?.avatar?.username || session?.avatar?.ice_username || session?.rtc?.ice_username || session?.ice_username;
        const cred = session?.avatar?.credential || session?.avatar?.ice_credential || session?.rtc?.ice_credential || session?.ice_credential;

        if (servers) {
          console.log('[WS] Got ICE servers, setting up WebRTC');
          setStatus('Setting up video connection...');
          setupWebRTC(servers, username, cred);
        }
      } else if (msg.server_sdp || msg.sdp || msg.answer) {
        handleAnswer(msg);
        setConnected(true);
        setStatus('Avatar connected — ready to present');
      } else if (msg.type === 'error') {
        setStatus(`Error: ${msg.error?.message || 'Unknown error'}`);
        console.error('[WS] Error:', msg.error);
      }
    } catch (err) {
      console.error('[WS] Parse error:', err);
    }
  }, [setupWebRTC, handleAnswer]);

  const startSession = useCallback(async () => {
    try {
      setStatus('Connecting to avatar service...');

      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${location.host}/ws/voice`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected, sending session config');
        setStatus('Configuring avatar session...');
        ws.send(JSON.stringify({
          type: 'session.update',
          session: {
            language,
            avatar: { character: 'lisa', style: 'casual-sitting' },
          },
        }));
      };

      ws.onmessage = handleMessage;

      ws.onerror = (e) => {
        console.error('[WS] Error:', e);
        setStatus('WebSocket connection failed');
      };

      ws.onclose = (e) => {
        console.log('[WS] Closed:', e.code, e.reason);
        if (!connected) {
          setStatus(`Connection closed: ${e.reason || 'unknown'}`);
        }
      };
    } catch (err: any) {
      setStatus(`Connection failed: ${err.message || err}`);
      console.error('Avatar connection error:', err);
    }
  }, [language, handleMessage, connected]);

  const speak = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const slide = presentation.slides[currentSlide];
    const text = slide?.notes || slide?.body || slide?.title || '';
    if (!text) {
      setStatus('No text to speak for this slide');
      return;
    }

    let speakText = text;
    if (language !== 'en-US') {
      setStatus('Translating...');
      try {
        const res = await translateText(text, language);
        speakText = res.translated_text;
      } catch {
        setStatus('Translation failed, speaking original');
      }
    }

    setSpeaking(true);
    setStatus(`Speaking slide ${currentSlide + 1}...`);

    // Send text to avatar via the realtime API conversation
    wsRef.current.send(JSON.stringify({
      type: 'conversation.item.create',
      item: {
        type: 'message',
        role: 'user',
        content: [{ type: 'input_text', text: `Please say the following exactly as written: ${speakText}` }],
      },
    }));
    wsRef.current.send(JSON.stringify({ type: 'response.create' }));

    // Speaking state will be cleared when we get response.done
    setTimeout(() => {
      setSpeaking(false);
      setStatus('Done speaking');
    }, 5000);
  }, [currentSlide, language, presentation]);

  const stopSession = useCallback(() => {
    try {
      wsRef.current?.close();
      wsRef.current = null;
      peerConnectionRef.current?.close();
      peerConnectionRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
    } catch {}
    setConnected(false);
    setSpeaking(false);
    setStatus('Disconnected');
  }, []);

  useEffect(() => {
    return () => { stopSession(); };
  }, []);

  return (
    <div style={styles.container}>
      <div style={styles.title}>🤖 AI Avatar</div>
      <div style={styles.videoContainer}>
        <video ref={videoRef} style={styles.video} autoPlay playsInline />
        {!connected && <div style={{ ...styles.placeholder, position: 'absolute' as const }}>
          Connect to start the avatar
        </div>}
      </div>
      <div style={styles.controls}>
        {!connected ? (
          <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={startSession}>
            ▶ Connect Avatar
          </button>
        ) : (
          <>
            <button
              style={{ ...styles.btn, ...styles.btnPrimary, ...(speaking ? styles.btnDisabled : {}) }}
              disabled={speaking}
              onClick={speak}
            >
              🎙️ Speak Slide {currentSlide + 1}
            </button>
            <button style={{ ...styles.btn, ...styles.btnDanger }} onClick={stopSession}>
              ⏹ Disconnect
            </button>
          </>
        )}
      </div>
      <div style={styles.status}>{status}</div>
    </div>
  );
}
