#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Face — rosto reativo com wake word, TTS e ASR
- Wake word: "OLA" (interrupção global)
- Preferência: Edge-TTS (online), fallback: pyttsx3 (offline)
- ASR: SpeechRecognition (Google Web Speech) com auto-escolha de microfone externo
- Janela em segunda tela (sem borda), render Pygame, expressões vetoriais suaves
"""

import os, sys, math, random, time, threading, queue, re, tempfile, asyncio
import pygame
from pygame import gfxdraw

# ===================== CORES =====================
BG   = (30, 39, 52)
CYAN = (46, 235, 215)
RED  = (248, 82, 82)

# ===================== CONFIG BÁSICA =====================
EXPRESSIONS = ["happy_open", "smile_eyes", "wink"]  # ciclo automático quando IDLE
INTERVAL_SECONDS = 1.2
FPS_TARGET = 45
OVERSAMPLE = 1.25
FACE_SCALE = 1.30

TARGET_DISPLAY = 1               # 0=principal, 1=segunda tela
BORDERLESS_SECONDARY = True
ANGRY_DURATION_MS = 1500
SAD_DURATION_MS   = 3000         # quanto tempo mantém a expressão triste

VERBOSE_LOG = True

# ===================== TTS CONFIG =====================
ENABLE_TTS         = True
USE_EDGE_TTS_FIRST = True

# Edge-TTS (vozes do Azure Speech):
EDGE_TTS_VOICE = "pt-BR-AntonioNeural"   # masculina PT-BR
EDGE_TTS_RATE  = "+0%"
EDGE_TTS_PITCH = "+0Hz"

# pyttsx3 fallback:
PYTTSX3_RATE   = 170
PYTTSX3_VOLUME = 1.0
VOICE_ID_OVERRIDE = ""  # opcional: ID SAPI5 para forçar

# Frases padrão
INTRO_DELAY_MS = 2000
INTRO_PHRASE   = "Olá! Eu sou o seu assistente. Diga 'OLA' para falar comigo."
LISTENING_PROMPT = "Estou ouvindo."
OUCH_PHRASE    = "Ai! Isso dói!"
DIDNT_GET_IT   = "Desculpe, não entendi. Pode repetir?"

# ===================== ASR CONFIG =====================
ENABLE_ASR          = True
ASR_ENERGY          = 300     # sensibilidade
ASR_PAUSE           = 0.6
ASR_TIMEOUT         = 5
ASR_PHRASE_TIMEOUT  = 5

# Wake word
WAKE_WORDS          = ["unip"]
COMMAND_WINDOW_MS   = 7000

MIC_PREFERRED_HINTS = ["usb", "external", "headset", "mic", "microfone", "logitech", "hyperx", "fifine"]

# ===================== VIEWBOX =====================
VW, VH = 800.0, 600.0
VCX, VCY = VW / 2, VH / 2

# ===================== UTIL DESENHO =====================
def to_screen(surface, x, y):
    W, H = surface.get_size()
    s_base = min(W / VW, H / VH)
    s = s_base * FACE_SCALE
    cx, cy = W / 2, H / 2
    sx = cx + (x - VCX) * s
    sy = cy + (y - VCY) * s
    return sx, sy, s

def aa_filled_circle(surf, x, y, r, color):
    gfxdraw.filled_circle(surf, int(round(x)), int(round(y)), int(round(r)), color)
    gfxdraw.aacircle(surf, int(round(x)), int(round(y)), int(round(r)), color)

def stroke_quad_bezier(surf, p0, p1, p2, width, color, steps=180):
    rad = max(1, int(round(width / 2)))
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t)**2 * p0[0] + 2*(1 - t)*t*p1[0] + t**2*p2[0]
        y = (1 - t)**2 * p0[1] + 2*(1 - t)*t*p1[1] + t**2*p2[1]
        aa_filled_circle(surf, x, y, rad, color)

def stroke_line_caps(surf, x1, y1, x2, y2, w, color):
    steps = max(6, int(max(abs(x2 - x1), abs(y2 - y1)) / 2))
    rad = max(1, int(round(w / 2)))
    for i in range(steps + 1):
        t = i / steps
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        aa_filled_circle(surf, x, y, rad, color)

# ===================== PARTES DO ROSTO =====================
def eyes_default(surface, s):
    for cx in (240, 560):
        x, y, _ = to_screen(surface, cx, 250)
        aa_filled_circle(surface, x, y, 60 * s, CYAN)

def eyes_color(surface, s, color):
    for cx in (240, 560):
        x, y, _ = to_screen(surface, cx, 250)
        aa_filled_circle(surface, x, y, 60 * s, color)

def eyes_smile_arcs(surface, s):
    p0 = to_screen(surface, 180, 250)
    p1 = to_screen(surface, 240, 210)
    p2 = to_screen(surface, 300, 250)
    stroke_quad_bezier(surface, (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1]), 20 * s, CYAN)
    p0 = to_screen(surface, 500, 250)
    p1 = to_screen(surface, 560, 210)
    p2 = to_screen(surface, 620, 250)
    stroke_quad_bezier(surface, (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1]), 20 * s, CYAN)

def eye_wink_right(surface, s):
    x, y, _ = to_screen(surface, 240, 250)
    aa_filled_circle(surface, x, y, 60 * s, CYAN)
    p0 = to_screen(surface, 520, 250)
    p1 = to_screen(surface, 560, 235)
    p2 = to_screen(surface, 600, 250)
    stroke_quad_bezier(surface, (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1]), 20 * s, CYAN)

def mouth_smile(surface, s):
    p0 = to_screen(surface, 310, 400)
    p1 = to_screen(surface, 400, 470)
    p2 = to_screen(surface, 490, 400)
    stroke_quad_bezier(surface, (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1]), 30 * s, CYAN)

def mouth_sad(surface, s):
    p0 = to_screen(surface, 310, 400)
    p1 = to_screen(surface, 400, 330)
    p2 = to_screen(surface, 490, 400)
    stroke_quad_bezier(surface, (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1]), 30 * s, CYAN)

def mouth_flat_red(surface, s):
    x1, y1, _ = to_screen(surface, 325, 400)
    x2, y2, _ = to_screen(surface, 475, 400)
    stroke_line_caps(surface, x1, y1, x2, y2, 30 * s, RED)

def mouth_talking_flat_top_round_bottom(surface, s):
    (x1, y1, _ ) = to_screen(surface, 330, 390)
    (x2, y2, _ ) = to_screen(surface, 470, 470)
    w = int(round(x2 - x1)); h = int(round(y2 - y1))
    rect = pygame.Rect(int(round(x1)), int(round(y1)), w, h)
    r = int(round(28 * to_screen(surface, 1, 1)[2]))
    pygame.draw.rect(surface, CYAN, rect, border_radius=0,
                     border_top_left_radius=0, border_top_right_radius=0,
                     border_bottom_left_radius=r, border_bottom_right_radius=r)

def draw_expression(surface, name):
    surface.fill(BG)
    _, _, s = to_screen(surface, 0, 0)
    if name == "happy_open":
        eyes_default(surface, s); mouth_smile(surface, s)
    elif name == "sad":
        eyes_default(surface, s); mouth_sad(surface, s)
    elif name == "angry":
        eyes_color(surface, s, RED)
        x1,y1,_ = to_screen(surface,200,160); x2,y2,_ = to_screen(surface,280,180)
        stroke_line_caps(surface,x1,y1,x2,y2,12*s,RED)
        x1,y1,_ = to_screen(surface,520,180); x2,y2,_ = to_screen(surface,600,160)
        stroke_line_caps(surface,x1,y1,x2,y2,12*s,RED)
        mouth_flat_red(surface, s)
    elif name == "smile_eyes":
        eyes_smile_arcs(surface, s); mouth_smile(surface, s)
    elif name == "wink":
        eye_wink_right(surface, s)
        p0 = to_screen(surface,330,400); p1 = to_screen(surface,400,450); p2 = to_screen(surface,470,400)
        stroke_quad_bezier(surface,(p0[0],p0[1]),(p1[0],p1[1]),(p2[0],p2[1]),30*s,CYAN)
    elif name == "talking":
        eyes_default(surface, s); mouth_talking_flat_top_round_bottom(surface, s)

# ===================== POSICIONAMENTO NA TELA 2 =====================
def _windows_monitor_rects():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_long),
                        ("rcMonitor", RECT), ("rcWork", RECT),
                        ("dwFlags", ctypes.c_long)]
        rects = []
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double
        )
        def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi))
            r = mi.rcMonitor
            rects.append((r.left, r.top, r.right, r.bottom))
            return 1
        user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_cb), 0)
        return rects if rects else None
    except Exception:
        return None

def create_on_display(display_index=1, borderless=True):
    if sys.platform.startswith("win"):
        rects = _windows_monitor_rects()
        if rects and 0 <= display_index < len(rects):
            left, top, right, bottom = rects[display_index]
            w, h = right - left, bottom - top
            os.environ['SDL_VIDEO_WINDOW_POS'] = f"{left},{top}"
            flags = pygame.NOFRAME if borderless else 0
            screen = pygame.display.set_mode((w, h), flags)
            try: pygame.display.set_window_position(left, top)
            except Exception: pass
            print(f"[INFO] Janela na tela {display_index} (WinAPI): pos=({left},{top}) size=({w}x{h})")
            return screen
        else:
            print("[AVISO] WinAPI indisponível; usando fallback SDL.")
    info = pygame.display
    num = (info.get_num_video_displays() if hasattr(info, "get_num_video_displays")
           else info.get_num_displays())
    if num <= display_index:
        print(f"[AVISO] Só há {num} monitor(es); usando janela normal.")
        return pygame.display.set_mode((1280, 720))
    sizes = info.get_desktop_sizes()
    w, h = sizes[display_index]
    x = sum(s[0] for s in sizes[:display_index]); y = 0
    os.environ['SDL_VIDEO_WINDOW_POS'] = f"{x},{y}"
    flags = pygame.NOFRAME if borderless else 0
    screen = pygame.display.set_mode((w, h), flags)
    try: pygame.display.set_window_position(x, y)
    except Exception: pass
    print(f"[INFO] Janela na tela {display_index} (SDL): pos=({x},{y}) size=({w}x{h})")
    return screen

# ===================== TTS (EDGE + FALLBACK) =====================
class TTSEngine:
    """
    Abstrai Edge-TTS (preferencial) com fallback para pyttsx3.
    Usa pygame.mixer para tocar o áudio gerado (MP3).
    """
    def __init__(self, prefer_edge=True):
        self.prefer_edge = prefer_edge
        self.edge_ok = False
        self.pytts_ok = False
        self.speaking_flag = False
        self._init_audio()

        if self.prefer_edge:
            self.edge_ok = self._probe_edge()
            if not self.edge_ok:
                self.pytts_ok = self._probe_pytts()
        else:
            self.pytts_ok = self._probe_pytts()
            if not self.pytts_ok:
                self.edge_ok = self._probe_edge()

        if VERBOSE_LOG:
            print(f"[TTS] edge_ok={self.edge_ok}  pyttsx3_ok={self.pytts_ok}")

    def _init_audio(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception as e:
            print("[AUDIO] Falha ao iniciar pygame.mixer:", e)

    def _probe_edge(self):
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def _probe_pytts(self):
        try:
            import pyttsx3
            self._pytts = pyttsx3.init()
            self._pytts.setProperty("rate", PYTTSX3_RATE)
            self._pytts.setProperty("volume", PYTTSX3_VOLUME)
            try:
                voices = self._pytts.getProperty("voices") or []
                chosen = None
                if VOICE_ID_OVERRIDE:
                    for v in voices:
                        if v.id == VOICE_ID_OVERRIDE: chosen = v; break
                if chosen is None and voices:
                    def score(v):
                        desc = f"{v.name} {getattr(v,'gender','')} {v.id}".lower()
                        s = 0
                        if any(w in desc for w in ["pt-br","português","brazil"]): s += 5
                        if any(w in desc for w in ["male","masculino"]): s += 4
                        for n in ["daniel","eduardo","ricardo","felipe","raul","antonio","guilherme"]:
                            if n in desc: s += 3
                        g = getattr(v,"gender","")
                        if isinstance(g,str) and g.lower().startswith("male"): s += 4
                        return s
                    chosen = sorted(voices, key=score, reverse=True)[0]
                if chosen:
                    self._pytts.setProperty("voice", chosen.id)
            except Exception:
                pass
            try:
                self._pytts.connect('started-utterance', lambda name: self._set_speaking(True))
                self._pytts.connect('finished-utterance', lambda name, completed: self._set_speaking(False))
                self._pytts.startLoop(False)
                self._pytts_loop_started = True
            except Exception:
                self._pytts_loop_started = False
            return True
        except Exception as e:
            if VERBOSE_LOG: print("[pyttsx3] indisponível:", e)
            return False

    def _set_speaking(self, v:bool):
        self.speaking_flag = v

    def speaking(self):
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            return True
        return bool(self.speaking_flag)

    def iterate(self):
        try:
            if getattr(self, "_pytts_loop_started", False):
                self._pytts.iterate()
        except Exception:
            pass

    async def _edge_tts_to_file(self, text, out_path):
        import edge_tts
        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH)
        with open(out_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

    def say(self, text):
        if not ENABLE_TTS or not text:
            return
        if self.edge_ok:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    tmp_path = tmp.name
                asyncio.run(self._edge_tts_to_file(text, tmp_path))
                self._set_speaking(True)
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                return
            except Exception as e:
                print("[Edge-TTS] falhou, tentando pyttsx3:", e)
        if self.pytts_ok:
            try:
                self._pytts.say(text)
            except Exception as e:
                print("[pyttsx3] erro em say():", e)

    def say_now(self, text):
        if not ENABLE_TTS or not text:
            return
        if self.edge_ok:
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                self.say(text)
                return
            except Exception:
                pass
        if self.pytts_ok:
            try:
                self._pytts.stop()
                self._pytts.say(text)
            except Exception as e:
                print("[pyttsx3] erro em say_now():", e)

# ===================== ASR (thread) =====================
def _choose_mic_index(hints=MIC_PREFERRED_HINTS):
    """Tenta escolher um microfone externo por nome; senão retorna None (default)."""
    try:
        import speech_recognition as sr
        names = sr.Microphone.list_microphone_names() or []
        if names:
            for i, n in enumerate(names):
                low = (n or "").lower()
                if any(h in low for h in hints):
                    if VERBOSE_LOG: print(f"[ASR] Usando microfone preferido: [{i}] {n}")
                    return i
            if len(names) > 1:
                if VERBOSE_LOG: print(f"[ASR] Usando microfone alternativo: [{len(names)-1}] {names[-1]}")
                return len(names) - 1
            if VERBOSE_LOG: print("[ASR] Usando microfone padrão do sistema.")
            return None
    except Exception as e:
        if VERBOSE_LOG: print("[ASR] Falha ao listar microfones:", e)
    return None

class ASRThread(threading.Thread):
    def __init__(self, out_queue, enable=True):
        super().__init__(daemon=True)
        self.enable = enable
        self.out_q = out_queue
        self._stop = threading.Event()
        self._mic_index = None

    def run(self):
        if not self.enable:
            return
        try:
            import speech_recognition as sr
        except Exception as e:
            print("[ASR] SpeechRecognition não disponível:", e)
            return

        r = sr.Recognizer()
        r.energy_threshold = ASR_ENERGY
        r.pause_threshold = ASR_PAUSE

        self._mic_index = _choose_mic_index()

        try:
            with sr.Microphone(device_index=self._mic_index) as mic:
                if VERBOSE_LOG:
                    print(f"[ASR] Mic ativo: {self._mic_index} | Ajustando ao ruído...")
                r.adjust_for_ambient_noise(mic, duration=1)
                if VERBOSE_LOG: print("[ASR] Pronto. Ouvindo...")
                while not self._stop.is_set():
                    try:
                        audio = r.listen(mic, timeout=ASR_TIMEOUT, phrase_time_limit=ASR_PHRASE_TIMEOUT)
                        text = ""
                        try:
                            text = r.recognize_google(audio, language="pt-BR")
                        except sr.UnknownValueError:
                            text = ""
                        except Exception as e:
                            if VERBOSE_LOG: print("[ASR] Erro:", e)
                            text = ""
                        if text:
                            if VERBOSE_LOG: print("[ASR] Ouvi:", text)
                            self.out_q.put(text)
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        if VERBOSE_LOG: print("[ASR] Captura erro:", e)
                        time.sleep(0.2)
        except Exception as e:
            print("[ASR] Microfone indisponível:", e)

    def stop(self):
        self._stop.set()

# ===================== NLU SIMPLES =====================
def parse_intent(text):
    if not text: return (None, {})
    t = text.lower()

    if re.search(r"\b(pare|parar|stop|chega)\b", t):
        return ("stop", {})

    if "me siga" in t or "siga-me" in t or "me acompanha" in t or "me acompanhar" in t:
        return ("follow_person", {})

    m = re.search(r"vá\s+para\s+a?\s*(cozinha|sala|quarto|banheiro|garagem|entrada)", t)
    if m:
        return ("navigate", {"room": m.group(1)})

    if "quem é você" in t or "quem e você" in t or "se apresente" in t or "como você se chama" in t:
        return ("introduce", {})

    if "piada" in t:
        return ("joke", {})

    if "como você está" in t or "tudo bem" in t or "como vai" in t:
        return ("status", {})

    if any(k in t for k in ["triste", "chateado", "poxa", "pena", "decepcionado"]):
        return ("make_sad", {})
    if any(k in t for k in ["feliz", "contente", "legal", "bom trabalho", "mandou bem"]):
        return ("make_happy", {})

    return (None, {})

def handle_intent(intent, slots):
    if intent == "stop":
        return ("Ok, parando por agora.", "happy_open")
    if intent == "follow_person":
        return ("Certo, vou te acompanhar. Fique à minha frente, por favor.", "smile_eyes")
    if intent == "navigate":
        room = slots.get("room","")
        return (f"Indo para a {room}.", "wink")
    if intent == "introduce":
        return ("Eu sou um assistente de serviço. Posso conversar, seguir você e executar tarefas simples.", "talking")
    if intent == "joke":
        return ("Por que o robô foi ao médico? Porque ele estava com parafusos soltos!", "smile_eyes")
    if intent == "status":
        return ("Estou bem e pronto para ajudar!", "happy_open")
    if intent == "make_sad":
        return ("Sinto muito por isso. Vou tentar melhorar.", "sad")
    if intent == "make_happy":
        return ("Que bom ouvir isso! Obrigado!", "happy_open")
    return (None, None)

def contains_wake_word(text):
    t = (text or "").lower()
    return any(w in t for w in WAKE_WORDS)

def strip_wake(text):
    t = text
    for w in WAKE_WORDS:
        t = re.sub(w, "", t, flags=re.IGNORECASE)
    return t.strip()

def clear_queue(q):
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass

# ===================== LOOP PRINCIPAL =====================
def main():
    pygame.init()
    pygame.display.set_caption("Rosto Interativo — UNIP Wake Word + Edge-TTS")
    screen = create_on_display(TARGET_DISPLAY, borderless=BORDERLESS_SECONDARY)

    clock = pygame.time.Clock()
    pygame.mouse.set_visible(False)

    # TTS
    tts = TTSEngine(prefer_edge=USE_EDGE_TTS_FIRST)

    # ASR
    asr_q = queue.Queue()
    asr_thread = ASRThread(asr_q, enable=ENABLE_ASR)
    if ENABLE_ASR:
        asr_thread.start()

    # Estados
    STATE_IDLE, STATE_AWAKE, STATE_EXEC = 0, 1, 2
    state = STATE_IDLE
    awake_until = 0
    said_fallback_this_window = False  # evita repetir "não entendi" dentro da mesma janela

    current = "happy_open"
    last_ms = pygame.time.get_ticks()
    start_ms = last_ms
    intro_done = False
    angry_until = 0
    sad_until   = 0
    last_ouch_ms = -999999
    OUCH_COOLDOWN_MS = 1200

    running = True
    try:
        while running:
            now = pygame.time.get_ticks()

            # Eventos de janela/teclado/toque
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif e.key == pygame.K_RIGHT:
                        current = random.choice(EXPRESSIONS); last_ms = now
                    elif e.key == pygame.K_UP:
                        globals()['FACE_SCALE'] = min(1.70, FACE_SCALE + 0.05)
                    elif e.key == pygame.K_DOWN:
                        globals()['FACE_SCALE'] = max(0.80, FACE_SCALE - 0.05)
                elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    angry_until = now + ANGRY_DURATION_MS
                    if now - last_ouch_ms >= OUCH_COOLDOWN_MS:
                        tts.say_now(OUCH_PHRASE)
                        last_ouch_ms = now

            # Intro depois de 2s
            if not intro_done and (now - start_ms) >= INTRO_DELAY_MS:
                intro_done = True
                tts.say(INTRO_PHRASE)

            # Consome ASR (não bloqueante)
            heard = None
            try:
                heard = asr_q.get_nowait()
            except queue.Empty:
                pass

            if heard:
                # ======== UNIP = interrupção global ========
                if contains_wake_word(heard):
                    tts.say_now(LISTENING_PROMPT)   # para fala atual e confirma escuta
                    clear_queue(asr_q)              # limpa fila atrasada
                    remainder = strip_wake(heard)

                    if remainder:
                        # UNIP + comando na mesma frase
                        intent, slots = parse_intent(remainder)
                        reply, expr = handle_intent(intent, slots)
                        if not reply:
                            reply = DIDNT_GET_IT
                            expr  = "sad"
                            sad_until = now + SAD_DURATION_MS
                        tts.say(reply)
                        current = expr or "happy_open"
                        state = STATE_EXEC                 # ao terminar de falar → IDLE
                    else:
                        # Só “UNIP”: entra em AWAKE
                        state = STATE_AWAKE
                        awake_until = now + COMMAND_WINDOW_MS
                        said_fallback_this_window = False

                else:
                    # ======== Sem wake word ========
                    if state == STATE_IDLE:
                        # ignora silenciosamente no IDLE
                        if VERBOSE_LOG:
                            print("[HRI] Ignorado (sem wake word):", heard)

                    elif state == STATE_AWAKE:
                        # tenta entender como comando
                        intent, slots = parse_intent(heard)
                        reply, expr = handle_intent(intent, slots)
                        if not reply:
                            if not said_fallback_this_window:
                                tts.say(DIDNT_GET_IT)
                                said_fallback_this_window = True
                                sad_until = now + SAD_DURATION_MS
                            # continua em AWAKE até expirar ou ouvir UNIP
                        else:
                            tts.say(reply)
                            current = expr or "happy_open"
                            state = STATE_EXEC

                    elif state == STATE_EXEC:
                        # executando (falando) — ignora até terminar ou ouvir UNIP
                        pass

            # expira janela AWAKE
            if state == STATE_AWAKE and now >= awake_until:
                state = STATE_IDLE

            # terminou de falar? se estava EXEC, volta a IDLE
            if state == STATE_EXEC and not tts.speaking():
                state = STATE_IDLE

            # Prioridade visual: angry > falando > sad > idle/atual
            if now < angry_until:
                expr_to_draw = "angry"
            elif tts.speaking():
                expr_to_draw = "talking"
            elif now < sad_until:
                expr_to_draw = "sad"
            else:
                if state == STATE_IDLE and (now - last_ms) >= int(INTERVAL_SECONDS * 1000):
                    current = random.choice(EXPRESSIONS)
                    last_ms = now
                expr_to_draw = current

            # Render
            w, h = screen.get_size()
            hi = pygame.Surface((int(w * OVERSAMPLE), int(h * OVERSAMPLE)))
            draw_expression(hi, expr_to_draw)
            pygame.transform.smoothscale(hi, (w, h), screen)
            pygame.display.flip()

            # Mantém pyttsx3 fluindo (se em fallback)
            tts.iterate()

            clock.tick_busy_loop(FPS_TARGET)
    finally:
        try:
            if ENABLE_ASR: asr_thread.stop()
        except Exception:
            pass
        pygame.quit()
