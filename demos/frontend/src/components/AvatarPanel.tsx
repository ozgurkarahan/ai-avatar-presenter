import React, { useState, useRef, useEffect, useCallback } from 'react';
import { type Presentation } from '../services/api';
import { useAuth } from '../services/auth';
import { pickDefaultAvatar, useAvatars } from '../services/avatars';
import { GateNotice } from './AuthGate';
import { demoCloseMessage, formatMinutes } from '../services/demo';

function formatClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

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
  /**
   * Visual mode for the avatar tile.
   * - 'wide' (default, legacy): 16:9 framing matching older prebuilt avatars.
   * - 'portrait': 1:1 close-up framing tuned for photo avatars.
   *   Mirrors the server-side `crop=560:560:660:20` head-zoom used by
   *   video_compose.py so the live stream matches the rendered MP4 framing.
   */
  mode?: 'wide' | 'portrait';
  /**
   * Who drives the session.
   * - 'admin' (default): `/ws/voice`, full controls (signed-in allowlisted users).
   * - 'demo': anonymous narration-only `/ws/voice/demo` — the server picks the
   *   avatar/voice/language and reads the stored slide notes itself.
   */
  access?: 'admin' | 'demo';
  /** Demo only: server-side session cap (from `GET /api/demo/config`). */
  demoSessionSeconds?: number;
}

const styles: Record<string, React.CSSProperties> = {
  container: { textAlign: 'center' as const },
  title: {
    fontSize: '14px',
    fontWeight: 600,
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    minHeight: '36px',
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
  videoContainerPortrait: {
    width: '100%',
    aspectRatio: '1 / 1',
    background: '#1a1a2e',
    borderRadius: '14px',
    overflow: 'hidden',
    position: 'relative' as const,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 8px 28px rgba(0, 51, 102, 0.18)',
  },
  video: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
  },
  videoPortrait: {
    width: '100%',
    height: '100%',
    objectFit: 'contain' as const,
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

export default function AvatarPanel({ presentation, currentSlide, language, onSlideChange, videoPlaying = false, onRequestVideoAutoPlay, selectedAvatar, selectedVoice, autoStart = false, mode = 'wide', access = 'admin', demoSessionSeconds = 180 }: Props) {
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
  const auth = useAuth();
  const isDemo = access === 'demo';
  const isDemoRef = useRef(isDemo);
  useEffect(() => { isDemoRef.current = isDemo; }, [isDemo]);
  const canUseAvatar = !auth.loading && auth.is_admin && !isDemo;
  // 'signin' / 'forbidden' when /ws/voice was refused with close code 4401 / 4403.
  const [authBlock, setAuthBlock] = useState<null | 'signin' | 'forbidden'>(null);
  // Demo-only UI state.
  const [demoConnecting, setDemoConnecting] = useState(false);
  const [demoEndsAt, setDemoEndsAt] = useState<number | null>(null);
  const [demoNow, setDemoNow] = useState(() => Date.now());
  const demoSecondsRef = useRef(demoSessionSeconds);
  useEffect(() => { demoSecondsRef.current = demoSessionSeconds; }, [demoSessionSeconds]);
  useEffect(() => {
    if (!demoEndsAt) return;
    const t = setInterval(() => setDemoNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [demoEndsAt]);
  const { avatars } = useAvatars();
  const defaultAvatarIdRef = useRef<string>('');
  useEffect(() => { defaultAvatarIdRef.current = pickDefaultAvatar(avatars)?.id ?? ''; }, [avatars]);

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

    // TURN over TCP/TLS 443 as fallback: Azure only advertises UDP 3478, which
    // proxies and firewalls that block UDP cannot reach.
    servers = servers.map((s: any) => {
      const entry = typeof s === 'string' ? { urls: s } : s;
      const urls: string[] = Array.isArray(entry.urls) ? entry.urls : [entry.urls];
      const extra = urls.flatMap((u) => {
        const host = /^turns?:([^:?]+)/.exec(u)?.[1];
        return host ? [`turn:${host}:443?transport=tcp`, `turns:${host}:443?transport=tcp`] : [];
      });
      return { ...entry, urls: Array.from(new Set([...urls, ...extra])) };
    });

    // Relay-only: on corporate / NAT-heavy networks the host and srflx pairs
    // never connect and ICE fails before it falls back to the TURN relay.
    const pc = new RTCPeerConnection({
      iceServers: servers,
      bundlePolicy: 'max-bundle',
      iceTransportPolicy: 'relay',
    });
    peerConnectionRef.current = pc;

    pc.oniceconnectionstatechange = () => {
      console.log('[WebRTC] ICE state:', pc.iceConnectionState);
    };

    // Report the real media state: signalling success does not mean video flows.
    pc.onconnectionstatechange = () => {
      if (peerConnectionRef.current !== pc) return;
      if (pc.connectionState === 'connected') {
        setConnected(true);
        setStatus((s) => (s.startsWith('Reconnected') ? s : 'Avatar connected — ready to present'));
      } else if (pc.connectionState === 'failed') {
        stopSessionRef.current();
        setStatus('Video connection failed — your network blocks the avatar stream. Try another network.');
      }
    };
    setTimeout(() => {
      if (peerConnectionRef.current === pc && pc.connectionState !== 'connected') {
        stopSessionRef.current();
        setStatus('Video connection timed out — your network blocks the avatar stream. Try another network.');
      }
    }, 20000);

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

      // Demo-only acks / notices from the server-side message filter.
      if (msg.type === 'demo.speaking') {
        spokenTextLengthRef.current = typeof msg.chars === 'number' ? msg.chars : 0;
        speechStartTimeRef.current = Date.now();
        if (safetyTimeoutRef.current) clearTimeout(safetyTimeoutRef.current);
        const safetyDuration = Math.min((spokenTextLengthRef.current / 13) + 30, 120);
        safetyTimeoutRef.current = setTimeout(() => {
          safetyTimeoutRef.current = null;
          advanceAfterSpeech();
        }, safetyDuration * 1000);
        return;
      }
      if (msg.type === 'demo.notice') {
        if (safetyTimeoutRef.current) { clearTimeout(safetyTimeoutRef.current); safetyTimeoutRef.current = null; }
        setSpeaking(false);
        const slideNo = (typeof msg.slide === 'number' ? msg.slide : currentSlideRef.current) + 1;
        if (msg.code === 'empty_slide') {
          setStatus(`No narration for slide ${slideNo}`);
          if (presentingRef.current) {
            const nextSlide = currentSlideRef.current + 1;
            if (nextSlide < presentation.slide_count) {
              onSlideChange(nextSlide);
              setTimeout(() => speakSlideRef.current(nextSlide), 1100);
            } else {
              setPresenting(false);
              setStatus('Presentation complete!');
            }
          }
        } else if (msg.code === 'rate_limited' && presentingRef.current) {
          setTimeout(() => speakSlideRef.current(currentSlideRef.current), 1200);
        } else {
          if (msg.code === 'speak_limit') setPresenting(false);
          setStatus(typeof msg.message === 'string' ? msg.message : 'Request ignored');
        }
        return;
      }

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
          retryCountRef.current = 0;
          setStatus('Connecting video…');
        }
      } else if ((msg.server_sdp || msg.sdp || msg.answer) && (!msg.type || msg.type === 'session.avatar.connected')) {
        handleAnswer(msg);
        retryCountRef.current = 0;
        if (pendingReconnectSpeakRef.current) {
          pendingReconnectSpeakRef.current = false;
          setStatus('Reconnected — speaking in new language...');
          setTimeout(() => speakSlideRef.current(currentSlideRef.current), 1000);
        } else {
          setStatus('Connecting video…');
        }
      } else if (msg.type === 'error') {
        const errMsg = msg.error?.message || 'Unknown error';
        console.error('[WS] Error:', msg.error);
        if (errMsg.toLowerCase().includes('capacity') && retryCountRef.current < 3 && !isDemoRef.current) {
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

  // Demo: release media + timers after the server ends the session (time cap, quota...).
  const teardownDemoMedia = useCallback(() => {
    if (speechTimeoutRef.current) { clearTimeout(speechTimeoutRef.current); speechTimeoutRef.current = null; }
    if (safetyTimeoutRef.current) { clearTimeout(safetyTimeoutRef.current); safetyTimeoutRef.current = null; }
    try {
      peerConnectionRef.current?.close();
      peerConnectionRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      document.querySelectorAll('audio[autoplay]').forEach((el) => el.remove());
    } catch {}
    setConnected(false);
    setSpeaking(false);
    setPresenting(false);
    setPaused(false);
    setDemoConnecting(false);
    setDemoEndsAt(null);
  }, []);

  const startDemoSession = useCallback(() => {
    if (wsRef.current) return;
    setStatus('Connecting to the demo avatar...');
    setDemoConnecting(true);
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws/voice/demo?deck_id=${encodeURIComponent(presentation.id)}`);
    wsRef.current = ws;
    let opened = false;
    ws.onopen = () => {
      opened = true;
      // No session.update: the server owns the whole demo session config.
      setStatus('Starting the avatar...');
      setDemoEndsAt(Date.now() + demoSecondsRef.current * 1000);
    };
    ws.onmessage = (event) => handleMessageRef.current(event);
    ws.onerror = (e) => { console.error('[WS] Demo error:', e); };
    ws.onclose = (e) => {
      console.log('[WS] Demo closed:', e.code, e.reason);
      if (wsRef.current !== ws) return; // user pressed Stop
      wsRef.current = null;
      teardownDemoMedia();
      const friendly = demoCloseMessage(e.code, opened);
      setStatus((prev) => friendly
        ?? (prev.startsWith('Error') ? prev : opened ? 'Demo ended' : 'Could not start the demo, try again later'));
    };
  }, [presentation.id, teardownDemoMedia]);

  useEffect(() => { if (connected) setDemoConnecting(false); }, [connected]);

  const startSession = useCallback(async () => {
    if (isDemoRef.current) {
      startDemoSession();
      return;
    }
    try {
      setStatus('Connecting to avatar service...');

      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${location.host}/ws/voice`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected, sending session config with language:', languageRef.current);
        setStatus('Configuring avatar session...');
        // Avatar ids come from GET /api/avatars; the backend voice proxy maps the
        // id to the Speech character/style server-side. Without an id, the
        // backend default avatar is used.
        const avatarId = selectedAvatarRef.current || defaultAvatarIdRef.current;
        const sessionConfig: Record<string, unknown> = {
          language: languageRef.current,
        };
        if (avatarId) sessionConfig.avatar = { character: avatarId, style: '' };
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
        if (e.code === 4401 || e.code === 4403) {
          setAuthBlock(e.code === 4401 ? 'signin' : 'forbidden');
          setStatus(e.code === 4401 ? 'Sign-in required for the live avatar' : "Your account isn't enabled for this demo");
          if (wsRef.current === ws) wsRef.current = null;
          return;
        }
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
  }, [language, connected, startDemoSession]);

  useEffect(() => { startSessionRef.current = startSession; }, [startSession]);

  // Speak a specific slide by index — reads languageRef so it always uses the latest language
  const speakSlide = useCallback(async (slideIndex: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const slide = presentation.slides[slideIndex];
    if (isDemoRef.current) {
      // The server looks up and reads the stored narration for this slide;
      // the visitor never sends text. Duration is refined on `demo.speaking`.
      setSpeaking(true);
      speechStartTimeRef.current = Date.now();
      spokenTextLengthRef.current = 0;
      setStatus(`Speaking slide ${slideIndex + 1} of ${presentation.slide_count}...`);
      if (safetyTimeoutRef.current) clearTimeout(safetyTimeoutRef.current);
      safetyTimeoutRef.current = setTimeout(() => {
        safetyTimeoutRef.current = null;
        advanceAfterSpeech();
      }, 120 * 1000);
      wsRef.current.send(JSON.stringify({ type: 'demo.speak', slide: slide?.index ?? slideIndex }));
      return;
    }
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
    setDemoConnecting(false);
    setDemoEndsAt(null);
    setStatus('Disconnected');
  }, []);

  useEffect(() => { stopSessionRef.current = stopSession; }, [stopSession]);

  useEffect(() => {
    return () => { stopSession(); };
  }, []);

  // Auto-start: connect on mount, and auto-present whenever the deck changes (playlist mode)
  const autoStartedForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoStart || !canUseAvatar || authBlock) return;
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
  }, [autoStart, connected, presentation.id, canUseAvatar, authBlock]);

  return (
    <div style={styles.container}>
      <div style={styles.title}>🤖 AI Avatar</div>
      <div style={mode === 'portrait' ? styles.videoContainerPortrait : styles.videoContainer}>
        <video
          ref={videoRef}
          style={mode === 'portrait' ? styles.videoPortrait : styles.video}
          autoPlay
          playsInline
        />
        {!connected && <div style={{ ...styles.placeholder, position: 'absolute' as const }}>
          {isDemo
            ? (demoConnecting ? 'Starting the avatar…' : 'Live avatar demo')
            : canUseAvatar && !authBlock ? 'Connect to start the avatar' : 'Live avatar preview'}
        </div>}
      </div>
      {isDemo ? (
        <div data-testid="demo-avatar-controls">
          <div style={styles.controls}>
            {!connected ? (
              <button
                type="button"
                data-testid="demo-start"
                style={{ ...styles.btn, ...styles.btnPrimary, ...(demoConnecting ? styles.btnDisabled : {}) }}
                disabled={demoConnecting}
                onClick={startSession}
              >
                {demoConnecting ? '… Starting' : '▶ Try the live demo'}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  style={{ ...styles.btn, ...styles.btnPrimary, ...(speaking ? styles.btnDisabled : {}) }}
                  disabled={speaking}
                  onClick={speak}
                >
                  🎙️ Present this slide
                </button>
                {!presenting && (
                  <button
                    type="button"
                    style={{ ...styles.btn, ...styles.btnSuccess, ...(speaking ? styles.btnDisabled : {}) }}
                    disabled={speaking}
                    onClick={startPresenting}
                  >
                    ▶️ Present all
                  </button>
                )}
              </>
            )}
            {(connected || demoConnecting) && (
              <button type="button" style={{ ...styles.btn, ...styles.btnDanger }} onClick={stopSession}>
                ⏹ Stop
              </button>
            )}
          </div>
          <div style={{ ...styles.status, color: '#475569' }}>
            Narration-only demo · up to {formatMinutes(demoSessionSeconds)} · no uploads
            {demoEndsAt && connected
              ? ` · ⏱ ${formatClock(Math.max(0, Math.round((demoEndsAt - demoNow) / 1000)))} left`
              : ''}
          </div>
          <div style={styles.status} role="status">{status === 'Not connected' ? '' : status}</div>
        </div>
      ) : !auth.loading && (!canUseAvatar || authBlock) ? (
        <div style={{ marginTop: 12 }}>
          <GateNotice action="try the live avatar" force={authBlock ?? undefined} />
          {authBlock && auth.is_admin && (
            <button
              type="button"
              onClick={() => { setAuthBlock(null); setStatus('Not connected'); }}
              style={{ ...styles.btn, marginTop: 8, background: 'transparent', color: '#005599' }}
            >
              ↻ Retry
            </button>
          )}
        </div>
      ) : (
      <>
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
      </>
      )}
    </div>
  );
}
