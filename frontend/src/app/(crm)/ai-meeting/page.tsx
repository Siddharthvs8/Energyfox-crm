'use client';
import { APP_SLUG } from "@/lib/config";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getApiBase } from "@/lib/mock-data";

// ─── SVGs & Icons ──────────────────────────────────────────────
const Icons = {
  Mic: ({ muted, className='' }: any) => (
    <svg className={className} width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      {muted ? (
        <><line x1="1" y1="1" x2="23" y2="23" /><path d="M9 9v3a3 3 0 005.12 2.12M15 9.34V4a3 3 0 00-5.94-.6" /><path d="M17 16.95A7 7 0 015 12v-2m14 0v2a7 7 0 01-.11 1.23" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" /></>
      ) : (
        <><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" /><path d="M19 10v2a7 7 0 01-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" /></>
      )}
    </svg>
  ),
  Camera: ({ off, className='' }: any) => (
    <svg className={className} width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      {off ? (
        <><path d="M16 16v1a2 2 0 01-2 2H3a2 2 0 01-2-2V7a2 2 0 012-2h2m5.66 0H14a2 2 0 012 2v3.34" /><path d="M23 7l-7 5 7 5V7z" /><line x1="1" y1="1" x2="23" y2="23" /></>
      ) : (
        <><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" /></>
      )}
    </svg>
  ),
  Phone: ({ className=''}: any) => (
    <svg className={className} width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
      <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1L6.6 10.8z"/>
    </svg>
  ),
  Type: ({ className='' }: any) => (
    <svg className={className} width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="4 7 4 4 20 4 20 7" /><line x1="9" y1="20" x2="15" y2="20" /><line x1="12" y1="4" x2="12" y2="20" />
    </svg>
  ),
  Send: ({ className='' }: any) => (
    <svg className={className} width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  ),
  Sparkles: ({ className='' }: any) => (
    <svg className={className} width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
       <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  )
};

// ─── MAANG Level AI Orb Component ──────────────────────────────
function AIOrb({ speaking, processing }: { speaking: boolean, processing?: boolean }) {
  // A glowing, breathing orb that scales vividly when speaking
  return (
    <div className="relative flex items-center justify-center w-64 h-64">
      {/* Outer Glows */}
      <div className={`absolute inset-0 rounded-full blur-[60px] opacity-60 transition-all duration-700 ease-in-out ${speaking ? 'bg-cyan-500 scale-125 opacity-100' : (processing ? 'bg-purple-600 scale-110 opacity-80' : 'bg-indigo-600 scale-100')}`} />
      <div className={`absolute inset-4 rounded-full blur-[40px] opacity-80 transition-all duration-500 ease-in-out ${speaking ? 'bg-blue-400 scale-110' : (processing ? 'bg-pink-500' : 'bg-blue-600')}`} />
      
      {/* Core AI Entity */}
      <div className={`relative w-40 h-40 rounded-full overflow-hidden transition-all duration-500 ${speaking ? 'scale-110' : 'scale-100'} flex items-center justify-center isolate`}>
         {/* Base gradient */}
         <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500 via-purple-500 to-cyan-500 opacity-80" />
         {/* Animated spinning layers for glassmorphism */}
         <div className={`absolute -inset-4 bg-gradient-to-bl from-transparent via-white/40 to-transparent blur-md rounded-full ${speaking ? 'animate-[spin_2s_linear_infinite]' : 'animate-[spin_8s_linear_infinite]'}`} />
         <div className={`absolute -inset-2 bg-gradient-to-tr from-transparent via-cyan-300/30 to-purple-400/30 blur-sm rounded-full ${speaking ? 'animate-[spin_3s_linear_infinite_reverse]' : 'animate-[spin_10s_linear_infinite_reverse]'}`} />
         
         {/* Inner glassy highlight */}
         <div className="absolute inset-2 rounded-full border border-white/30 bg-gradient-to-b from-white/20 to-transparent" />
         
         {/* Core intensity */}
         <div className={`w-16 h-16 rounded-full bg-white opacity-40 blur-[15px] ${speaking ? 'animate-pulse scale-150' : 'scale-100'}`} />
      </div>

      {speaking && (
        <>
            <div className="absolute inset-0 rounded-full border-2 border-cyan-400/50 animate-ping delay-100" />
            <div className="absolute inset-0 rounded-full border border-blue-400/30 animate-ping delay-300" />
        </>
      )}
    </div>
  );
}

// ─── MOM Modal ──────────────────────────────────────────────────
function MOMModal({ mom, onClose, sessionType, agentName }: any) {
  const downloadMOM = () => {
    const blob = new Blob([mom], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url;
    a.download = `MOM_${sessionType}_${agentName}_${new Date().toLocaleDateString('en-IN').replace(/\//g, '-')}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center p-4 lg:p-8 animate-in fade-in duration-300">
      <div className="bg-[#111111] border border-white/10 rounded-3xl shadow-2xl w-full max-w-3xl flex flex-col overflow-hidden max-h-[90vh]">
        <div className="border-b border-white/10 p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-gradient-to-r from-indigo-900/20 to-purple-900/10">
          <div>
            <h2 className="text-white font-bold text-2xl tracking-tight flex items-center gap-2"><Icons.Sparkles className="text-yellow-400 w-6 h-6"/> Meeting Summary</h2>
            <p className="text-slate-400 text-sm mt-1">{sessionType} Session · {agentName}</p>
          </div>
          <button onClick={downloadMOM} className="flex items-center justify-center gap-2 px-5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full text-white text-sm font-medium transition-all shadow-lg">
             Export TXT
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <pre className="text-[15px] text-slate-300 whitespace-pre-wrap leading-relaxed font-sans">{mom}</pre>
        </div>
        <div className="p-6 bg-black/40 border-t border-white/5 flex justify-end">
          <button onClick={onClose} className="px-8 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-full hover:from-indigo-500 hover:to-purple-500 transition-all shadow-lg shadow-indigo-900/50">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Page Component ──────────────────────────────────────────────
export default function AIMeetingPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;

  const [callState, setCallState] = useState<'lobby' | 'call' | 'ended'>('lobby');
  const [session, setSession] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [meetingConfig, setMeetingConfig] = useState<any>(null);
  const [userName, setUserName] = useState('You');
  const [mom, setMom] = useState<string | null>(null);
  const [showMOM, setShowMOM] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Media
  const [micMuted, setMicMuted] = useState(false);
  const [camOff, setCamOff] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // AI & Voice
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [interimText, setInterimText] = useState('');
  const transcriptBufferRef = useRef<string>('');
  const throttleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const recognitionRef = useRef<any>(null);
  const shouldListenRef = useRef(false);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  // Interaction
  const [showTextInput, setShowTextInput] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isEnding, setIsEnding] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const api = useCallback((url: string, opts?: any) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem(`${domain}_access`) : null;
    return fetch(`${getApiBase(domain)}${url}`, {
      ...opts,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts?.headers || {}) },
    });
  }, [domain]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
        const synth = window.speechSynthesis;
        synth.getVoices(); // pre-warm voices
        const savedName = localStorage.getItem(`${domain}_username`);
        if (savedName) setUserName(savedName);
    }
    const init = async () => {
      try {
        const configR = await api('/api/ai-manager/meeting-config/');
        if (configR.ok) setMeetingConfig(await configR.json());
        const checkR = await api('/api/ai-manager/meeting-check/');
        if (checkR.ok) {
           const data = await checkR.json();
           if (data.active_session) {
               setSession(data.active_session);
               setMessages(data.active_session.messages || []);
           }
        }
      } catch (e) {}
      setIsLoading(false);
    };
    init();
  }, [api, domain]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, interimText, isProcessing]);

  // STT Logic
  const startListening = useCallback(() => {
    if (typeof window === 'undefined' || aiSpeaking || micMuted || isProcessing) return;
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
        setErrorMsg("Voice input not supported in this browser. Please use text.");
        setShowTextInput(true);
        return;
    }

    try {
        if (recognitionRef.current) recognitionRef.current.stop();
        const recognition = new SpeechRec();
        recognitionRef.current = recognition;
        recognition.lang = meetingConfig?.meeting_language || 'en-US';
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onstart = () => { setUserSpeaking(true); setErrorMsg(''); };
        recognition.onend = () => {
            setUserSpeaking(false);
            if (shouldListenRef.current && !aiSpeaking && !micMuted && callState === 'call') {
                try { recognition.start(); } catch(e) {}
            }
        };

        recognition.onerror = (e: any) => {
            if (e.error === 'not-allowed') {
                setErrorMsg("Microphone access denied.");
                setShowTextInput(true);
                setMicMuted(true);
            }
        };

        recognition.onresult = (event: any) => {
            let interim = '';
            let final = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) final += event.results[i][0].transcript;
                else interim += event.results[i][0].transcript;
            }

            if (interim) setInterimText(interim);
            if (final) {
                transcriptBufferRef.current += ' ' + final.trim();
                setInterimText('');
                
                if (throttleTimerRef.current) clearTimeout(throttleTimerRef.current);
                throttleTimerRef.current = setTimeout(() => {
                    const txt = transcriptBufferRef.current.trim();
                    if (txt && !aiSpeaking && !isProcessing) {
                        transcriptBufferRef.current = '';
                        sendMessage(txt);
                    }
                }, 800); // 800ms pause signifies end of thought
            }
        };
        recognition.start();
    } catch(e) { console.error("[STT]", e); }
  }, [aiSpeaking, micMuted, isProcessing, meetingConfig, callState]);

  const stopListening = useCallback(() => {
    shouldListenRef.current = false;
    try { recognitionRef.current?.stop(); } catch(e) {}
    setUserSpeaking(false);
  }, []);

  // TTS Logic
  const speakAI = useCallback((text: string, langCode?: string) => {
    if (typeof window === 'undefined' || !text) return;
    const synth = window.speechSynthesis;
    synthRef.current = synth;
    synth.cancel();
    stopListening();

    const utterance = new SpeechSynthesisUtterance(text);
    const lang = langCode || meetingConfig?.meeting_language || 'en-US';
    const prefix = lang.split('-')[0];
    const voices = synth.getVoices();
    let voice = voices.find(v => v.lang === lang);
    if (!voice) voice = voices.find(v => v.lang.startsWith(prefix) && !v.name.toLowerCase().includes('google'));
    if (!voice) voice = voices.find(v => v.lang.startsWith(prefix));
    
    if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }
    else utterance.lang = lang;

    utterance.onstart = () => { setAiSpeaking(true); };
    utterance.onend = () => { 
        setAiSpeaking(false);
        if (callState === 'call' && !micMuted) {
            shouldListenRef.current = true;
            setTimeout(startListening, 300);
        }
    };
    utterance.onerror = () => {
        setAiSpeaking(false);
        if (callState === 'call' && !micMuted) {
             shouldListenRef.current = true;
             startListening();
        }
    };
    synth.speak(utterance);
  }, [meetingConfig, callState, micMuted, startListening, stopListening]);

  // Messaging
  const sendMessage = async (text: string) => {
    if (!text.trim() || isProcessing || !session) return;
    stopListening();
    setIsProcessing(true);
    setErrorMsg('');

    const mId = Date.now();
    setMessages(prev => [...prev, { id: mId, sender_type: 'user', content: text, timestamp: new Date().toISOString() }]);

    try {
        const res = await api(`/api/ai-manager/meeting-sessions/${session.id}/chat/`, { method: 'POST', body: JSON.stringify({ message: text }) });
        if (res.ok) {
            const data = await res.json();
            setMessages(prev => [...prev, { id: mId+1, sender_type: 'ai', content: data.ai_reply, timestamp: new Date().toISOString() }]);
            speakAI(data.ai_reply, meetingConfig?.meeting_language);
        } else {
            setErrorMsg("Failed to send message. AI might be rate limited.");
            shouldListenRef.current = true;
            startListening();
        }
    } catch(e) {
        setErrorMsg("Network error.");
        shouldListenRef.current = true;
        startListening();
    }
    setIsProcessing(false);
  };

  const joinCall = async () => {
      setCallState('call');
      try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          setStream(stream);
          if (videoRef.current) videoRef.current.srcObject = stream;
      } catch(e) {
          setCamOff(true);
          setMicMuted(true);
          setShowTextInput(true);
          setErrorMsg("No camera/microphone found. You are in text mode.");
      }

      let active = (session && session.status === 'active') ? session : null;
      if (!active) {
          try {
              const res = await api('/api/ai-manager/meeting-start/', { method: 'POST' });
              if (res.ok) {
                  const data = await res.json();
                  active = data.active_session;
                  setSession(active);
                  setMessages(active.messages || []);
              }
          } catch(e) {}
      }

      shouldListenRef.current = true;
      if (active?.messages?.length > 0) {
          const firstAI = active.messages.find((m:any) => m.sender_type === 'ai');
          if (firstAI) setTimeout(() => speakAI(firstAI.content, meetingConfig?.meeting_language), 1000);
      } else {
          startListening();
      }
  };

  const endCall = async () => {
      if (!session) return;
      stopListening();
      synthRef.current?.cancel();
      stream?.getTracks().forEach(t => t.stop());
      setIsEnding(true);

      try {
          const res = await api(`/api/ai-manager/meeting-sessions/${session.id}/end/`, { method: 'POST' });
          if (res.ok) {
              const data = await res.json();
              setMom(data.mom);
              setShowMOM(true);
              setSession((prev: any) => prev ? { ...prev, status: 'completed' } : null);
          }
      } catch(e) {}
      
      setIsEnding(false);
      setCallState('ended');
  };

  const toggleMic = () => {
      setMicMuted(prev => {
          const m = !prev;
          stream?.getAudioTracks().forEach(t => t.enabled = !m);
          if (m) stopListening();
          else { shouldListenRef.current = true; startListening(); }
          return m;
      });
  };

  const toggleCam = () => {
      setCamOff(prev => {
          const o = !prev;
          stream?.getVideoTracks().forEach(t => t.enabled = !o);
          return o;
      });
  };

  if (isLoading) return <div className="min-h-screen bg-[#050505] flex items-center justify-center text-white"><div className="animate-pulse">Loading Environment...</div></div>;

  if (isEnding) return (
      <div className="min-h-screen bg-[#050505] flex flex-col items-center justify-center text-white relative overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40vw] h-[40vw] rounded-full bg-indigo-900/30 blur-[100px] pointer-events-none" />
          <div className="relative z-10 flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shadow-xl mb-6">
                 <Icons.Sparkles className="w-8 h-8 text-indigo-400 animate-spin" style={{ animationDuration: '3s' }} />
              </div>
              <h2 className="text-xl font-semibold mb-2">Analyzing Session...</h2>
              <p className="text-slate-400 text-sm">Generating your Minutes of Meeting and final reports.</p>
          </div>
      </div>
  );

  if (callState === 'lobby' || callState === 'ended') {
    return (
        <div className="min-h-screen relative flex items-center justify-center bg-[#09090b] overflow-hidden">
            {/* Background elements */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[60vw] h-[60vw] rounded-full bg-indigo-900/20 blur-[120px] pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-full h-1/2 bg-gradient-to-t from-black to-transparent pointer-events-none" />
            
            <div className="relative z-10 w-full max-w-lg p-8 md:p-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
                <div className="flex flex-col items-center text-center space-y-6">
                    <div className="w-24 h-24 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-500 p-[2px] shadow-2xl shadow-indigo-500/30">
                        <div className="w-full h-full rounded-full bg-black flex items-center justify-center text-white">
                             <Icons.Sparkles className="w-10 h-10 text-white animate-pulse" />
                        </div>
                    </div>
                    <div>
                        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400 tracking-tight">Alex AI</h1>
                        <p className="text-slate-400 mt-3 text-sm leading-relaxed max-w-sm mx-auto">
                            Your intelligent sales manager. Discuss leads, track targets, and strategize in real-time.
                        </p>
                    </div>

                    {session?.status === 'active' && (
                        <div className="px-4 py-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full text-indigo-300 text-xs font-semibold uppercase tracking-widest animate-pulse">
                            Session Resumed
                        </div>
                    )}

                    <button onClick={joinCall} className="w-full py-4 mt-8 rounded-full bg-white text-black font-semibold text-lg transition-transform hover:scale-105 active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.3)]">
                        {session?.status === 'active' ? 'Rejoin Session' : 'Start Session'}
                    </button>
                    {callState === 'ended' && !showMOM && mom && (
                        <button onClick={() => setShowMOM(true)} className="text-slate-400 text-sm hover:text-white transition-colors mt-2">View Last Summary</button>
                    )}
                </div>
            </div>
            
            {showMOM && mom && <MOMModal mom={mom} onClose={() => setShowMOM(false)} sessionType={session?.session_type_display} agentName={userName} />}
        </div>
    );
  }

  // Active Call (MAANG Premium UI)
  return (
    <div className="min-h-screen bg-[#050505] text-white flex flex-col font-sans overflow-hidden relative">
      {/* Background Ambience */}
      <div className={`absolute top-0 inset-x-0 h-96 bg-gradient-to-b from-indigo-900/20 to-transparent pointer-events-none transition-opacity duration-1000 ${aiSpeaking ? 'opacity-100' : 'opacity-40'}`} />

      {/* Header */}
      <header className="relative z-20 flex items-center justify-between px-6 py-5 bg-[#0a0a0a] border-b border-white/5">
          <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
                  <Icons.Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                  <h1 className="font-bold text-base tracking-wide">Alex AI</h1>
                  <div className="flex items-center gap-2 mt-0.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                      <p className="text-xs text-slate-400 uppercase tracking-wider font-medium">{session?.session_type_display} Session</p>
                  </div>
              </div>
          </div>
          <div className="flex items-center gap-4">
             <div className="px-3 py-1 bg-white/10 rounded-md text-xs font-medium text-slate-300 uppercase tracking-wide border border-white/10">
                 {meetingConfig?.meeting_language.split('-')[0].toUpperCase() || 'EN'}
             </div>
          </div>
      </header>

      {/* Main Grid */}
      <main className="flex-1 flex flex-col lg:flex-row relative z-10 overflow-hidden">
          
          {/* Visualizer & Camera Section */}
          <section className="flex-shrink-0 lg:w-[40%] border-b lg:border-b-0 lg:border-r border-white/5 flex flex-col relative bg-black/20">
              
              {/* AI VISUALIZER */}
              <div className="flex-1 flex items-center justify-center min-h-[300px] relative overflow-hidden">
                 <AIOrb speaking={aiSpeaking} processing={isProcessing} />
                 {/* Voice status label */}
                 <div className="absolute bottom-8 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-black/90 rounded-full border border-white/10 text-xs font-medium text-slate-300 shadow-xl transition-all">
                    {aiSpeaking ? 'Alex is speaking...' : (isProcessing ? 'Thinking...' : (userSpeaking ? 'Listening...' : 'Alex is listening'))}
                 </div>
              </div>

              {/* USER CAMERA PIP */}
              <div className="h-48 lg:h-64 relative border-t border-white/5 bg-[#0a0a0a] p-4 shrink-0">
                  <div className="w-full h-full rounded-2xl overflow-hidden relative shadow-2xl ring-1 ring-white/10">
                      <video ref={videoRef} autoPlay playsInline muted className={`w-full h-full object-cover scale-x-[-1] transition-opacity duration-300 ${camOff ? 'opacity-0' : 'opacity-100'}`} />
                      {camOff && (
                          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#111] text-slate-500 gap-3">
                              <Icons.Camera off={true} className="w-8 h-8 opacity-50" />
                              <span className="text-xs font-medium uppercase tracking-widest">Camera Off</span>
                          </div>
                      )}
                      <div className="absolute bottom-3 left-3 flex items-center gap-2">
                         <div className="px-2.5 py-1.5 bg-black/90 rounded-lg border border-white/10 text-xs font-medium flex items-center gap-2 shadow-sm text-white">
                            {micMuted && <span className="text-red-400"><Icons.Mic muted={true} className="w-3.5 h-3.5" /></span>}
                            <span>{userName}</span>
                         </div>
                      </div>
                  </div>
              </div>
          </section>

          {/* Transcript Section */}
          <section className="flex-1 flex flex-col bg-transparent relative h-full lg:max-h-full">
              <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar scroll-smooth pb-32">
                  {messages.length === 0 && (
                      <div className="flex items-center justify-center h-full text-slate-600 font-medium text-sm">
                          Your conversation will appear here...
                      </div>
                  )}
                  {messages.map((m) => (
                      <div key={m.id} className={`flex ${m.sender_type === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
                          <div className={`max-w-[85%] lg:max-w-[70%] px-5 py-4 rounded-3xl text-[15px] leading-relaxed shadow-xl ${
                              m.sender_type === 'ai' 
                                ? 'bg-[#1a1a1a] border border-white/10 text-slate-100 rounded-tl-sm' 
                                : 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white rounded-tr-sm'}`}>
                             {m.content}
                          </div>
                      </div>
                  ))}
                  
                  {interimText && (
                      <div className="flex justify-end animate-in fade-in duration-200">
                          <div className="max-w-[85%] lg:max-w-[70%] px-5 py-4 rounded-3xl text-[15px] leading-relaxed bg-[#2d2a52] border border-indigo-500/20 text-white rounded-tr-sm italic shadow-xl">
                              {interimText}<span className="animate-pulse mx-1">|</span>
                          </div>
                      </div>
                  )}
                  {isProcessing && (
                      <div className="flex justify-start animate-in fade-in duration-200">
                          <div className="px-6 py-5 rounded-3xl rounded-tl-sm bg-[#1e1e1e] border border-white/5 flex items-center gap-2 shadow-xl">
                              <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{animationDelay: '0ms'}}/>
                              <div className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{animationDelay: '150ms'}}/>
                              <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{animationDelay: '300ms'}}/>
                          </div>
                      </div>
                  )}
                  <div ref={messagesEndRef} />
              </div>

              {/* Text Input Panel (Slide up) */}
              <div className={`absolute bottom-6 left-0 right-0 px-6 transition-all duration-300 ${showTextInput ? 'translate-y-0 opacity-100 visible' : 'translate-y-4 opacity-0 invisible z-[-1]'}`}>
                  {errorMsg && <div className="max-w-3xl mx-auto mb-2 px-3 py-1.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-xs text-center">{errorMsg}</div>}
                  <div className="max-w-3xl mx-auto bg-black p-2 rounded-2xl border border-white/10 shadow-2xl flex items-center focus-within:border-indigo-500/50">
                      <input 
                          type="text" 
                          className="flex-1 bg-transparent border-none text-white px-4 py-3 text-[15px] focus:outline-none placeholder-slate-500"
                          placeholder="Type your message here..."
                          value={textInput}
                          onChange={(e) => setTextInput(e.target.value)}
                          onKeyDown={(e) => { if(e.key === 'Enter') { sendMessage(textInput); setTextInput(''); } }}
                          disabled={isProcessing}
                      />
                      <button 
                          onClick={() => { sendMessage(textInput); setTextInput(''); }}
                          disabled={!textInput.trim() || isProcessing}
                          className="w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center text-white disabled:opacity-30 transition-colors mr-1 shadow-lg"
                        >
                          <Icons.Send className="w-4 h-4" />
                      </button>
                  </div>
              </div>
          </section>

      </main>

      {/* Control Dock */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="px-6 py-3 bg-[#111115] border border-white/10 rounded-full flex items-center gap-4 shadow-2xl">
              <button onClick={toggleMic} className={`w-14 h-14 flex items-center justify-center rounded-full transition-all duration-300 hover:scale-105 active:scale-95 shadow-xl ${micMuted ? 'bg-red-500/20 text-red-500 border border-red-500/30' : 'bg-white/10 text-white hover:bg-white/20 border border-white/5'}`}>
                 <Icons.Mic muted={micMuted} className="w-6 h-6" />
              </button>
              
              <button title="End Meeting" onClick={endCall} className="w-16 h-16 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white transition-all duration-300 hover:scale-110 active:scale-95 shadow-[0_0_30px_rgba(220,38,38,0.4)]">
                 <Icons.Phone className="w-7 h-7" />
              </button>
              
              <div className="flex gap-2">
                  <button onClick={toggleCam} className={`w-12 h-12 flex items-center justify-center rounded-full transition-all duration-300 hover:scale-105 active:scale-95 ${camOff ? 'bg-red-500/20 text-red-500 border border-red-500/30' : 'bg-white/10 text-slate-300 hover:text-white hover:bg-white/20 border border-white/5'}`}>
                     <Icons.Camera off={camOff} className="w-5 h-5" />
                  </button>
                  <button onClick={() => setShowTextInput(!showTextInput)} className={`w-12 h-12 flex items-center justify-center rounded-full transition-all duration-300 hover:scale-105 active:scale-95 ${showTextInput ? 'bg-indigo-600 text-white border border-indigo-500' : 'bg-white/10 text-slate-300 hover:text-white hover:bg-white/20 border border-white/5'}`}>
                     <Icons.Type className="w-5 h-5" />
                  </button>
              </div>
          </div>
      </div>

    </div>
  );
}
