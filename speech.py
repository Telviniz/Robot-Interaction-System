import speech_recognition as sr
from transformers import pipeline, AutoTokenizer, AutoModelForQuestionAnswering
import os
import pyttsx3

# Importações para filtro de ruído mantidas, caso queira reativar no futuro
import numpy as np
import noisereduce as nr

# --- PARTE 1: CONFIGURAÇÃO DOS MODELOS DE IA ---

# 1a. Configuração do Modelo de Perguntas e Respostas (QA)
PASTA_MODELO_RELATIVA = "modelo_qa_offline"
PASTA_MODELO_ABSOLUTA = os.path.abspath(PASTA_MODELO_RELATIVA)

print("[SETUP] Carregando o modelo de Perguntas e Respostas (QA)...")
print(f"  -> Procurando o modelo em: {PASTA_MODELO_ABSOLUTA}")

try:
    print("  -> Carregando tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(PASTA_MODELO_ABSOLUTA)
    print("  -> Carregando modelo principal...")
    model = AutoModelForQuestionAnswering.from_pretrained(PASTA_MODELO_ABSOLUTA)
    print("  -> Montando o pipeline final...")
    qa_pipeline = pipeline("question-answering", model=model, tokenizer=tokenizer)
    print("  -> Modelo de QA carregado com sucesso! (100% OFFLINE)")

except Exception as e:
    print(f"[ERRO CRÍTICO] Não foi possível carregar o modelo da pasta '{PASTA_MODELO_ABSOLUTA}'.")
    print(f"   -> DETALHE DO ERRO: {e}")
    exit()

# 1b. Configuração do Reconhecedor de Voz
r = sr.Recognizer()
MODELO_WHISPER_ATIVACAO = "tiny"
MODELO_WHISPER_PERGUNTA = "small.en"

print(f"[SETUP] Modelo de ativação ('wake word') carregado: '{MODELO_WHISPER_ATIVACAO}'")
print(f"[SETUP] Modelo de pergunta principal carregado: '{MODELO_WHISPER_PERGUNTA}'")

# <-- AJUSTE: REMOVIDA A CONFIGURAÇÃO GLOBAL DO TTS. ELA AGORA É FEITA DENTRO DA FUNÇÃO speak()


# --- PARTE 2: FUNÇÃO DE PERGUNTAS E RESPOSTAS ---
def responder_com_base_no_contexto(contextos: list, pergunta: str):
    print("\n--- INÍCIO DO LOG DE PROCESSAMENTO (QA) ---")
    print(f"[LOG] Pergunta recebida: '{pergunta}'")
    contexto_completo = " ".join(contextos)
    resultado = qa_pipeline(question=pergunta, context=contexto_completo)
    resposta = resultado['answer']
    confianca = resultado['score']
    print(f"[LOG] Resposta extraída: '{resposta}' (Confiança: {confianca:.4f})")
    print("--- FIM DO LOG DE PROCESSAMENTO (QA) ---")
    if confianca > 0.1:
        return resposta
    else:
        return "I could not find a reliable answer for that in my context."

# <-- AJUSTE PRINCIPAL: A LÓGICA DO MOTOR DE FALA FOI MOVIDA PARA DENTRO DA FUNÇÃO
def speak(text):
    """
    Converte um texto em fala.
    O motor é inicializado e finalizado a cada chamada para garantir que funcione
    corretamente dentro de um loop.
    """
    try:
        print(f"\n<< ROBOT SPEAKING: '{text}'")
        
        # 1. Inicializa uma nova instância do motor de TTS
        tts_engine = pyttsx3.init()
        
        # 2. Procura e configura a voz em inglês
        voices = tts_engine.getProperty('voices')
        english_voice = next((voice for voice in voices if 'EN-US' in voice.id), None)
        if english_voice:
            tts_engine.setProperty('voice', english_voice.id)
        
        # 3. Coloca o texto na fila para ser falado
        tts_engine.say(text)
        
        # 4. Processa a fila, fala e aguarda a conclusão
        tts_engine.runAndWait()
        
    except Exception as e:
        print(f"[ERRO NO TTS] Não foi possível falar: {e}")


# --- PARTE 3: CONTEXTOS PARA O ROBÔ ---
context_robot_A_en = """Service robots assist human beings...""" # Omitido para encurtar
context_robot_B_en = """Vitória is the fourth most populous city...""" # Omitido para encurtar
context_identity = "Your name is UD-H1."
contextos_gerais = [context_robot_A_en, context_robot_B_en, context_identity]
palavrachave = "Start"

# --- PARTE 4: LOOP PRINCIPAL SEM SUPRESSÃO DE RUÍDO ---
print(f"\n[INFO] Sistema pronto! Diga '{palavrachave}' para ativar.")
print("A sessão será encerrada após 6 perguntas.")
print("=======================================================")

question_count = 0
MAX_QUESTIONS = 6

while question_count < MAX_QUESTIONS:
    print(f"\n({question_count + 1}/{MAX_QUESTIONS}) Aguardando a palavra de ativação ('{palavrachave}')...")
    texto_detectado = ""
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            audio_ativacao = r.listen(source, phrase_time_limit=2)
            
            print("...Analisando palavra de ativação como inglês...")
            texto_detectado = r.recognize_whisper(audio_ativacao, model=MODELO_WHISPER_ATIVACAO, language="english").lower()

        if palavrachave.lower() in texto_detectado:
            print(f"Palavra de ativação detectada! (Ouvi: '{texto_detectado}')")
            print('\a')
            print("Estou ouvindo sua pergunta agora...")
            
            with sr.Microphone() as source_pergunta:
                r.adjust_for_ambient_noise(source_pergunta, duration=1)
                audio_pergunta_ruidoso = r.listen(source_pergunta, timeout=5, phrase_time_limit=10)

                if audio_pergunta_ruidoso.get_raw_data():
                    
                    print("Reconhecendo a pergunta com o modelo principal (sem filtro de ruído)...")
                    # Usando o áudio original (audio_pergunta_ruidoso) para o reconhecimento
                    comando_voz = r.recognize_whisper(audio_pergunta_ruidoso, model=MODELO_WHISPER_PERGUNTA, language="english")
                    
                    print(f"\n>> VOCÊ PERGUNTOU: '{comando_voz}'")

                    if comando_voz and comando_voz.strip():
                        resposta_final = responder_com_base_no_contexto(
                            contextos=contextos_gerais,
                            pergunta=comando_voz
                        )
                        print(f"\n<< RESPOSTA: '{resposta_final}'")
                        speak(resposta_final)
                        question_count += 1
                    else:
                        print("-> A pergunta reconhecida estava vazia. Tente novamente.")
                else:
                    print("-> Não detectei som para a pergunta. Tente novamente.")

        elif texto_detectado.strip():
            print(f"  (Ouvi: '{texto_detectado}', mas esperava por '{palavrachave}'...)")

    except sr.UnknownValueError:
        print("  (Não consegui entender o áudio captado.)")
        pass
    except sr.WaitTimeoutError:
        print("  (Nenhum som detectado no tempo limite.)")
        pass
    except sr.RequestError as e:
        print(f"-> Erro no motor Whisper; {e}")
    except KeyboardInterrupt:
        print("\n\nPrograma interrompido pelo usuário.")
        break
    except Exception as e:
        print(f"[ERRO INESPERADO] Ocorreu um problema: {e}")
        break

print("\n=======================================================")
print(f"Limite de {MAX_QUESTIONS} perguntas atingido. Encerrando o programa.")
