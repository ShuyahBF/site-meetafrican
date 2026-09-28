import { useEffect, useRef, useState } from "react";

const MAX_SECONDS = 180; // 3 minutes par note vocale

/** Format audio accepté par le navigateur (Opus/WebM partout, MP4 sur iPhone). */
function pickMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return candidates.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
}

/**
 * Enregistreur de note vocale : un tap pour commencer, un tap pour envoyer
 * (ou ✕ pour annuler). Si `transcribe` est vrai et que le navigateur sait
 * le faire (Chrome, Android…), la parole est aussi transcrite en texte
 * pendant l'enregistrement.
 * onSend({ blob, duration, transcript }) est appelé à l'envoi.
 */
export default function VoiceRecorder({ transcribe, onSend, onError, disabled, onRecordingChange }) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const startRef = useRef(0);
  const timerRef = useRef(null);
  const recognitionRef = useRef(null);
  const transcriptRef = useRef("");
  const cancelledRef = useRef(false);

  // Prévient le parent (masque le champ texte pendant l'enregistrement)
  useEffect(() => {
    onRecordingChange?.(recording);
  }, [recording]); // eslint-disable-line react-hooks/exhaustive-deps

  const stopAll = (cancel) => {
    cancelledRef.current = cancel;
    clearInterval(timerRef.current);
    try {
      recognitionRef.current?.stop();
    } catch {
      // déjà arrêtée
    }
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
  };

  // Nettoyage si on quitte la page en cours d'enregistrement
  useEffect(() => () => stopAll(true), []); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      onError?.("Votre navigateur ne permet pas d'enregistrer de note vocale.");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onError?.("Autorisez l'accès au micro pour envoyer une note vocale.");
      return;
    }
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunksRef.current = [];
    transcriptRef.current = "";
    cancelledRef.current = false;
    recorder.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop()); // libère le micro
      if (cancelledRef.current) return;
      const duration = Math.max(1, (Date.now() - startRef.current) / 1000);
      const blob = new Blob(chunksRef.current, { type: (recorder.mimeType || "audio/webm").split(";")[0] });
      onSend({ blob, duration, transcript: transcriptRef.current.trim() });
    };
    recorderRef.current = recorder;
    recorder.start();
    startRef.current = Date.now();
    setSeconds(0);
    setRecording(true);
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now() - startRef.current) / 1000);
      setSeconds(s);
      if (s >= MAX_SECONDS) stopAll(false); // durée maximale atteinte : envoi
    }, 250);

    // Transcription en direct (reconnaissance vocale du navigateur)
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (transcribe && Recognition) {
      const recognition = new Recognition();
      recognition.lang = "fr-FR";
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i += 1) {
          if (e.results[i].isFinal) transcriptRef.current += `${e.results[i][0].transcript} `;
        }
      };
      recognition.onerror = () => {};
      try {
        recognition.start();
        recognitionRef.current = recognition;
      } catch {
        recognitionRef.current = null;
      }
    }
  };

  const mm = String(Math.floor(seconds / 60));
  const ss = String(seconds % 60).padStart(2, "0");

  if (!recording) {
    return (
      <button
        type="button"
        onClick={start}
        disabled={disabled}
        aria-label="Enregistrer une note vocale"
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-lg shadow-primary/30 transition active:scale-90 disabled:opacity-40"
      >
        <span className="material-symbols-outlined">mic</span>
      </button>
    );
  }
  return (
    <div className="flex flex-1 items-center gap-2">
      <button type="button" onClick={() => stopAll(true)} aria-label="Annuler" className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-500">
        <span className="material-symbols-outlined">close</span>
      </button>
      <div className="flex h-12 flex-1 items-center gap-2 rounded-full bg-rose-50 px-4 text-sm font-bold text-rose-600">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-rose-500" />
        {mm}:{ss} {transcribe && <span className="truncate text-xs font-semibold text-rose-400">· transcription activée</span>}
      </div>
      <button type="button" onClick={() => stopAll(false)} aria-label="Envoyer la note vocale" className="flex h-12 w-12 items-center justify-center rounded-full bg-brand text-white shadow-lg shadow-primary/30">
        <span className="material-symbols-outlined">send</span>
      </button>
    </div>
  );
}
