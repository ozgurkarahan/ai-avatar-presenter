import React, { useState, useRef, useEffect, useCallback } from 'react';
import { type Presentation } from '../services/api';

interface Props {
  presentation: Presentation;
  currentSlide: number;
  language: string;
  onSlideChange: (index: number) => void;
  videoPlaying?: boolean;
  onRequestVideoAutoPlay?: () => void;
  selectedAvatar?: string;
  selectedVoice?: string;
  autoStart?: boolean;
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
  btnSuccess: {
    background: '#27ae60',
    color: 'white',
  },
  btnWarning: {
    background: '#e67e22',
    color: 'white',
  },
  status: {
    marginTop: '8px',
    fontSize: '12px',
    color: '#666',
  },
};

export default function AvatarPanel({ presentation, currentSlide, language, onSlideChange, videoPlaying = false, onRequestVideoAutoPlay, selectedAvatar, selectedVoice, autoStart = false }: Props) {
  const [connected, setConnected] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [presenting, setPresenting] = useState(false);
  const [status, setStatus] = useState('Not connected');
  const videoRef = useRef<HTMLVideoElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const presentingRef = useRef(false);
  const currentSlideRef = useRef(currentSlide);
  const languageRef = useRef(language);
  const speakSlideRef = useRef<(idx: number) => void>(() => {});
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingReconnectSpeakRef = useRef(false);
  const stopSessionRef = useRef<() => void>(() => {});
  const speechStartTimeRef = useRef(0);
  const spokenTextLengthRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safetyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleMessageRef = useRef<(event: MessageEvent) => void>(() => {});
  const prevVideoPlayingRef = useRef(videoPlaying);

  // When video starts playing, interrupt the avatar's speech
  useEffect(() => {
    if (!videoPlaying) return;
    if (!connected) return;
    // Cancel pending timers so auto-advance doesn't fire mid-video
    if (speechTimeoutRef.current) { clearTimeout(speechTimeoutRef.current); speechTimeoutRef.current = null; }
    if (safetyTimeoutRef.current) { clearTimeout(safetyTimeoutRef.current); safetyTimeoutRef.current = null; }
    setSpeaking(false);
    setStatus('⏸ Video playing — avatar paused');
    // Tell Azure to stop the current response immediately
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'response.cancel' }));
    }
  }, [videoPlaying, connected]);

  // When video ends while presenting, advance to the next slide
  useEffect(() => {
    const wasPlaying = prevVideoPlayingRef.current;
    prevVideoPlayingRef.current = videoPlaying;
    if (wasPlaying && !videoPlaying && presentingRef.current) {
      const nextSlide = currentSlideRef.current + 1;
      if (nextSlide < presentation.slide_count) {
        onSlideChange(nextSlide);
        setTimeout(() => speakSlideRef.current(nextSlide), 500);
      } else {
        setPresenting(false);
        setStatus('Presentation complete!');
      }
    }
  }, [videoPlaying, presentation.slide_count, onSlideChange]);

  // Keep refs in sync with state/props
  useEffect(() => { currentSlideRef.current = currentSlide; }, [currentSlide]);
  useEffect(() => { presentingRef.current = presenting; }, [presenting]);
  useEffect(() => { languageRef.current = language; }, [language]);
  useEffect(() => { pausedRef.current = paused; }, [paused]);
  const selectedAvatarRef = useRef(selectedAvatar);
  const selectedVoiceRef = useRef(selectedVoice);
  useEffect(() => { selectedAvatarRef.current = selectedAvatar; }, [selectedAvatar]);
  useEffect(() => { selectedVoiceRef.current = selectedVoice; }, [selectedVoice]);
  const prevLanguageRef = useRef(language);

  // When language changes while connected, tear down the session and reconnect with new language
  useEffect(() => {
    if (language === prevLanguageRef.current) return;
    prevLanguageRef.current = language;
    if (!connected) return;

    setStatus(`Switching language to ${language} — reconnecting avatar...`);
    pendingReconnectSpeakRef.current = true;
    // Full teardown, then reconnect with new language config
    stopSessionRef.current();
    // Small delay to let cleanup finish before reconnecting
    setTimeout(() => {
      startSessionRef.current();
    }, 500);
  }, [language, connected]);

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

    // Helper: send the current local SDP offer to the backend (idempotent)
    let sdpSent = false;
    const sendSdpOffer = () => {
      if (sdpSent || !pc.localDescription) return;
      sdpSent = true;
      const sdp = btoa(JSON.stringify({ type: 'offer', sdp: pc.localDescription.sdp }));
      console.log('[WebRTC] Sending SDP offer (ICE gathering state:', pc.iceGatheringState, ')');
      wsRef.current?.send(JSON.stringify({ type: 'session.avatar.connect', client_sdp: sdp }));
    };

    // When ICE gathering is complete, send the SDP offer to backend
    pc.onicecandidate = (e) => {
      if (!e.candidate && pc.localDescription) {
        console.log('[WebRTC] ICE gathering complete, sending SDP offer');
        sendSdpOffer();
      }
    };

    // Safety fallback: if ICE gathering doesn't complete in 5 s, send whatever we have
    pc.onicegatheringstatechange = () => {
      console.log('[WebRTC] ICE gathering state:', pc.iceGatheringState);
      if (pc.iceGatheringState === 'complete') {
        sendSdpOffer();
      }
    };
    setTimeout(() => {
      if (pc.iceGatheringState !== 'complete' && pc.localDescription) {
        console.warn('[WebRTC] ICE gathering timeout — sending SDP with gathered candidates');
        sendSdpOffer();
      }
    }, 5000);

    // Receive video/audio tracks from avatar
    pc.ontrack = (e) => {
      console.log('[WebRTC] Got track:', e.track.kind);
      if (e.track.kind === 'video' && videoRef.current) {
        videoRef.current.srcObject = e.streams[0];
        videoRef.current.play().catch(() => {});
      } else if (e.track.kind === 'audio') {
        // Remove any previous audio element
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current.remove();
        }
        const audio = document.createElement('audio');
        audio.srcObject = e.streams[0];
        audio.autoplay = true;
        audio.style.display = 'none';
        document.body.appendChild(audio);
        audioRef.current = audio;
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

  // Shared logic for advancing after speech finishes (used by response.done handler and safety timeout)
  const advanceAfterSpeech = useCallback(() => {
    // Cancel any pending timers
    if (speechTimeoutRef.current) {
      clearTimeout(speechTimeoutRef.current);
      speechTimeoutRef.current = null;
    }
    if (safetyTimeoutRef.current) {
      clearTimeout(safetyTimeoutRef.current);
      safetyTimeoutRef.current = null;
    }
    setSpeaking(false);
    // If pause was requested, stop after this slide finishes
    if (pausedRef.current) {
      setStatus(`Paused after slide ${currentSlideRef.current + 1}`);
      return;
    }
    setStatus('Done speaking');
    // Auto-advance to next slide if in presenting mode
    if (presentingRef.current) {
      const nextSlide = currentSlideRef.current + 1;
      if (nextSlide < presentation.slide_count) {
        console.log(`[Auto-advance] Moving to slide ${nextSlide + 1}`);
        onSlideChange(nextSlide);
        setTimeout(() => speakSlideRef.current(nextSlide), 500);
      } else {
        setPresenting(false);
        setStatus('Presentation complete!');
      }
    }
  }, [presentation.slide_count, onSlideChange]);

  // Handle incoming WebSocket messages from backend proxy
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data);
      console.log('[WS] Message:', msg.type || 'unknown');

      if (msg.type === 'proxy.connected') {
        setStatus('Connected to Azure Voice API');
      } else if (msg.type === 'session.updated' || msg.type === 'session.avatar.connecting') {
        const session = msg.session || msg;
        const servers = session?.avatar?.ice_servers || session?.rtc?.ice_servers || session?.ice_servers;
        const username = session?.avatar?.username || session?.avatar?.ice_username || session?.rtc?.ice_username || session?.ice_username;
        const cred = session?.avatar?.credential || session?.avatar?.ice_credential || session?.rtc?.ice_credential || session?.ice_credential;
        if (servers) {
          console.log('[WS] Got ICE servers from', msg.type, ', setting up WebRTC');
          setStatus('Setting up video connection...');
          setupWebRTC(servers, username, cred);
        }
        // session.avatar.connecting may also carry the server SDP answer
        const serverSdp = msg.server_sdp || msg.sdp;
        if (serverSdp) {
          console.log('[WS] server SDP received in', msg.type);
          handleAnswer(msg);
          setConnected(true);
          retryCountRef.current = 0;
          setStatus('Avatar connected — ready to present');
        }
      } else if ((msg.server_sdp || msg.sdp || msg.answer) && (!msg.type || msg.type === 'session.avatar.connected')) {
        handleAnswer(msg);
        setConnected(true);
        retryCountRef.current = 0;
        if (pendingReconnectSpeakRef.current) {
          pendingReconnectSpeakRef.current = false;
          setStatus('Reconnected — speaking in new language...');
          setTimeout(() => speakSlideRef.current(currentSlideRef.current), 1000);
        } else {
          setStatus('Avatar connected — ready to present');
        }
      } else if (msg.type === 'error') {
        const errMsg = msg.error?.message || 'Unknown error';
        console.error('[WS] Error:', msg.error);
        if (errMsg.toLowerCase().includes('capacity') && retryCountRef.current < 3) {
          retryCountRef.current += 1;
          const delay = retryCountRef.current * 5;
          setStatus(`Avatar busy — retrying in ${delay}s (attempt ${retryCountRef.current}/3)...`);
          try { wsRef.current?.close(); } catch {}
          wsRef.current = null;
          retryTimerRef.current = setTimeout(() => { startSessionRef.current(); }, delay * 1000);
        } else {
          setStatus(`Error: ${errMsg}`);
        }
      }

      // Completion signals — checked independently from the chain above
      // so they are never accidentally swallowed by an earlier branch.
      if (msg.type === 'response.done' || msg.type === 'response.output_item.done') {
        // Skip if a speech-advance timeout is already scheduled
        if (speechTimeoutRef.current) return;
        // For the weaker signal, skip if no speech is in progress
        if (msg.type === 'response.output_item.done' && !safetyTimeoutRef.current) return;

        console.log(`[WS] Completion signal: ${msg.type} — scheduling advance`);
        if (safetyTimeoutRef.current) {
          clearTimeout(safetyTimeoutRef.current);
          safetyTimeoutRef.current = null;
        }
        const elapsed = (Date.now() - speechStartTimeRef.current) / 1000;
        const estimatedDuration = spokenTextLengthRef.current / 13;
        const remaining = Math.min(Math.max(0, estimatedDuration - elapsed), 70);
        console.log(`[WS] Speech: ${estimatedDuration.toFixed(1)}s est, ${elapsed.toFixed(1)}s elapsed, wait ${remaining.toFixed(1)}s`);
        setStatus('Finishing speech...');
        speechTimeoutRef.current = setTimeout(() => {
          speechTimeoutRef.current = null;
          advanceAfterSpeech();
        }, remaining * 1000);
      }
    } catch (err) {
      console.error('[WS] Parse error:', err);
    }
  }, [setupWebRTC, handleAnswer, presentation.slide_count, onSlideChange, presentation, advanceAfterSpeech]);

  // Keep handleMessage ref in sync so the WS handler always uses the latest version
  useEffect(() => { handleMessageRef.current = handleMessage; }, [handleMessage]);

  const startSessionRef = useRef<() => void>(() => {});

  const startSession = useCallback(async () => {
    try {
      setStatus('Connecting to avatar service...');

      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${location.host}/ws/voice`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected, sending session config with language:', languageRef.current);
        setStatus('Configuring avatar session...');
        const avatarId = selectedAvatarRef.current || 'harry';
        const avatarStyleMap: Record<string, string> = {
          lisa: 'casual-sitting', harry: 'youthful', meg: 'business', max: 'business',
        };
        const sessionConfig: Record<string, unknown> = {
          avatar: { character: avatarId, style: avatarStyleMap[avatarId] ?? 'youthful' },
          language: languageRef.current,
        };
        if (selectedVoiceRef.current) {
          sessionConfig.voice = selectedVoiceRef.current;
        }
        ws.send(JSON.stringify({
          type: 'session.update',
          session: sessionConfig,
        }));
      };

      // Use ref to always call the latest handleMessage (avoids stale closure)
      ws.onmessage = (event) => handleMessageRef.current(event);

      ws.onerror = (e) => {
        console.error('[WS] Error:', e);
        setStatus('WebSocket connection failed');
      };

      ws.onclose = (e) => {
        console.log('[WS] Closed:', e.code, e.reason);
        const reason = e.reason || '';
        if (reason.toLowerCase().includes('capacity') && retryCountRef.current < 3) {
          retryCountRef.current += 1;
          const delay = retryCountRef.current * 5;
          setStatus(`Avatar busy — retrying in ${delay}s (attempt ${retryCountRef.current}/3)...`);
          retryTimerRef.current = setTimeout(() => {
            startSessionRef.current();
          }, delay * 1000);
        } else if (!connected) {
          setStatus(reason ? `Connection closed: ${reason}` : 'Connection closed');
        }
      };
    } catch (err: any) {
      setStatus(`Connection failed: ${err.message || err}`);
      console.error('Avatar connection error:', err);
    }
  }, [language, connected]);

  useEffect(() => { startSessionRef.current = startSession; }, [startSession]);

  // Speak a specific slide by index — reads languageRef so it always uses the latest language
  const speakSlide = useCallback(async (slideIndex: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const slide = presentation.slides[slideIndex];
    // If the slide has an embedded video, trigger auto-play and wait for it to finish
    if (slide?.video_url) {
      if (presentingRef.current) {
        setStatus(`▶ Playing video for slide ${slideIndex + 1}...`);
        onRequestVideoAutoPlay?.();
      }
      return;
    }
    const text = slide?.notes || slide?.body || slide?.title || '';
    if (!text) {
      setStatus(`No text to speak for slide ${slideIndex + 1}`);
      // If presenting, try next slide
      if (presentingRef.current) {
        const nextSlide = slideIndex + 1;
        if (nextSlide < presentation.slide_count) {
          onSlideChange(nextSlide);
          setTimeout(() => speakSlideRef.current(nextSlide), 500);
        } else {
          setPresenting(false);
          setStatus('Presentation complete!');
        }
      }
      return;
    }

    const lang = languageRef.current;
    let speakText = text;
    if (lang !== 'en-US') {
      // Use pre-translated notes from Cosmos DB cache (populated by batch job at upload + App.tsx)
      const cached = slide?.translated_notes?.[lang];
      if (cached) {
        speakText = cached;
      } else {
        setStatus(`No cached translation for ${lang} — speaking original`);
      }
    }

    setSpeaking(true);
    speechStartTimeRef.current = Date.now();
    spokenTextLengthRef.current = speakText.length;
    setStatus(`Speaking slide ${slideIndex + 1} of ${presentation.slide_count}...`);

    // Safety timeout: if response.done never arrives, force advance after estimated duration + buffer
    if (safetyTimeoutRef.current) clearTimeout(safetyTimeoutRef.current);
    const safetyDuration = Math.min((speakText.length / 13) + 30, 120); // estimated + 30s buffer, max 2 min
    safetyTimeoutRef.current = setTimeout(() => {
      safetyTimeoutRef.current = null;
      console.warn('[Safety] response.done not received — forcing advance after', safetyDuration.toFixed(0), 's');
      advanceAfterSpeech();
    }, safetyDuration * 1000);

    // The session is already configured with the correct language voice & instructions,
    // so we just ask the avatar to read the text as-is.
    const prompt = `Please say the following exactly as written: ${speakText}`;

    // Send text to avatar via the realtime API conversation
    wsRef.current.send(JSON.stringify({
      type: 'conversation.item.create',
      item: {
        type: 'message',
        role: 'user',
        content: [{ type: 'input_text', text: prompt }],
      },
    }));
    wsRef.current.send(JSON.stringify({ type: 'response.create' }));
    // Speaking state is cleared by response.done handler or safety timeout
  }, [presentation, onSlideChange, advanceAfterSpeech, onRequestVideoAutoPlay]);

  // Keep speakSlideRef in sync so stale closures (handleMessage timeouts) call the latest version
  useEffect(() => { speakSlideRef.current = speakSlide; }, [speakSlide]);

  const speak = useCallback(() => {
    speakSlide(currentSlide);
  }, [currentSlide, speakSlide]);

  // Start auto-presenting from the current slide through the end
  const startPresenting = useCallback(() => {
    setPresenting(true);
    setPaused(false);
    speakSlide(currentSlide);
  }, [currentSlide, speakSlide]);

  // Pause: let the current slide finish speaking, then stop auto-advancing
  const pauseSpeech = useCallback(() => {
    setPaused(true);
    setStatus(`Pausing after slide ${currentSlideRef.current + 1}...`);
  }, []);

  // Resume: advance to the next slide and continue presenting
  const resumeSpeech = useCallback(() => {
    setPaused(false);
    const nextSlide = currentSlideRef.current + 1;
    if (nextSlide < presentation.slide_count) {
      onSlideChange(nextSlide);
      setTimeout(() => speakSlideRef.current(nextSlide), 500);
    } else {
      setPresenting(false);
      setStatus('Presentation complete!');
    }
  }, [presentation.slide_count, onSlideChange]);

  const stopSession = useCallback(() => {
    // Cancel any pending retry
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    // Cancel any pending speech timeout
    if (speechTimeoutRef.current) {
      clearTimeout(speechTimeoutRef.current);
      speechTimeoutRef.current = null;
    }
    // Cancel any pending safety timeout
    if (safetyTimeoutRef.current) {
      clearTimeout(safetyTimeoutRef.current);
      safetyTimeoutRef.current = null;
    }
    retryCountRef.current = 0;
    try {
      // Tell Azure to close the session before dropping the connection
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'session.close' }));
      }
      wsRef.current?.close();
      wsRef.current = null;
      peerConnectionRef.current?.close();
      peerConnectionRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      // Clean up any orphaned audio elements
      document.querySelectorAll('audio[autoplay]').forEach((el) => el.remove());
    } catch {}
    setConnected(false);
    setSpeaking(false);
    setPresenting(false);
    setPaused(false);
    setStatus('Disconnected');
  }, []);

  useEffect(() => { stopSessionRef.current = stopSession; }, [stopSession]);

  useEffect(() => {
    return () => { stopSession(); };
  }, []);

  // Auto-start: connect on mount, and auto-present whenever the deck changes (path mode)
  const autoStartedForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoStart) return;
    if (!connected) {
      startSessionRef.current();
      return;
    }
    // Already connected — if presentation changed, auto-present from the current slide
    if (autoStartedForRef.current !== presentation.id) {
      autoStartedForRef.current = presentation.id;
      setPresenting(true);
      setPaused(false);
      setTimeout(() => speakSlideRef.current(currentSlideRef.current), 500);
    }
  }, [autoStart, connected, presentation.id]);

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
              style={{ ...styles.btn, ...styles.btnPrimary, ...(speaking || paused ? styles.btnDisabled : {}) }}
              disabled={speaking || paused}
              onClick={speak}
            >
              🎙️ Speak Slide {currentSlide + 1}
            </button>
            {speaking && paused ? (
              <button
                style={{ ...styles.btn, ...styles.btnWarning, ...styles.btnDisabled }}
                disabled
              >
                ⏸ Pausing...
              </button>
            ) : paused ? (
              <button
                style={{ ...styles.btn, ...styles.btnSuccess }}
                onClick={resumeSpeech}
              >
                ▶ Resume
              </button>
            ) : speaking ? (
              <button
                style={{ ...styles.btn, ...styles.btnWarning }}
                onClick={pauseSpeech}
              >
                ⏸ Pause
              </button>
            ) : !presenting ? (
              <button
                style={{ ...styles.btn, ...styles.btnSuccess }}
                onClick={startPresenting}
              >
                ▶️ Present All
              </button>
            ) : null}
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
