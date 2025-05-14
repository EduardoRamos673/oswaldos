import streamlit as st
import psycopg2
import pandas as pd
import qrcode
import os
import cv2
import numpy as np
from PIL import Image
from datetime import datetime, timezone

# ------------------ Configuración ------------------
DATABASE_URL_ENV = os.environ.get("postgresql://postgres.lqdsgwoeszsbqtlasxvt:Jajaja1298@aws-0-us-east-2.pooler.supabase.com:6543/postgres")  # Asegúrate de establecer esta variable en tu entorno

# ------------------ Datos de usuarios de ejemplo ------------------
USUARIOS = {
    "admin@correo.com": {"password": "admin123", "rol": "admin"},
    "user@correo.com": {"password": "user123", "rol": "usuario"}
}

# ------------------ Función de conexión ------------------
def obtener_conexion():
    if not DATABASE_URL_ENV:
        st.error("La variable de entorno 'DATABASE_URL' no está configurada.")
        return None
    try:
        return psycopg2.connect(DATABASE_URL_ENV)
    except Exception as err:
        st.error(f"No se pudo conectar a la base de datos: {err}")
        return None

# ------------------ Inicio de sesión ------------------
def login():
    st.title("🔐 Inicio de Sesión")
    correo = st.text_input("Correo electrónico")
    contraseña = st.text_input("Contraseña", type="password")
    if st.button("Iniciar Sesión"):
        usuario = USUARIOS.get(correo)
        if usuario and usuario["password"] == contraseña:
            st.session_state["autenticado"] = True
            st.session_state["usuario"] = correo
            st.session_state["rol"] = usuario["rol"]
            st.success(f"Bienvenido, {correo}")
            st.experimental_rerun()
        else:
            st.error("Correo o contraseña incorrectos.")

# ------------------ Crear QR ------------------
def crear_codigo_qr_simple(id_sesion):
    os.makedirs("codigos_qr", exist_ok=True)
    imagen_qr = qrcode.make(id_sesion)
    qr_path = f"codigos_qr/sesion_{id_sesion}.png"
    try:
        imagen_qr.save(qr_path)
        return qr_path
    except Exception as e:
        st.error(f"Error al guardar el QR: {e}")
        return None

# ------------------ Módulo: Generar QR ------------------
def modulo_generar_qr():
    st.header("📤 Crear Código QR para Asistencia")
    id_sesion = st.text_input("ID de la sesión (ej: MAT101-CLASE5)")
    if st.button("Crear QR") and id_sesion.strip():
        qr_path = crear_codigo_qr_simple(id_sesion)
        if qr_path:
            st.image(qr_path, caption=f"QR para: {id_sesion}")
            st.success(f"QR generado y guardado en: {qr_path}")

# ------------------ Módulo: Registrar Asistencia ------------------
def modulo_registro():
    st.header("📷 Registro de Asistencia")
    nombre_usuario = st.text_input("Nombre completo")
    correo_usuario = st.text_input("Correo electrónico")
    imagen_subida = st.camera_input("Escanea el código QR")

    if imagen_subida and nombre_usuario and correo_usuario:
        imagen_pil = Image.open(imagen_subida)
        id_sesion_leido = detectar_qr(imagen_pil)
        if id_sesion_leido:
            st.success(f"ID de sesión detectado: {id_sesion_leido}")
            conn = obtener_conexion()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO asistencias (sesion_id, nombre, correo, hora_registro)
                            VALUES (%s, %s, %s, %s)
                        """, (id_sesion_leido, nombre_usuario, correo_usuario, datetime.now(timezone.utc)))
                        conn.commit()
                        st.success("Asistencia registrada correctamente.")
                except psycopg2.IntegrityError as ie:
                    conn.rollback()
                    st.error(f"Error de integridad: {ie}")
                except psycopg2.Error as db_err:
                    conn.rollback()
                    st.error(f"Error en la base de datos: {db_err}")
                finally:
                    conn.close()
        else:
            st.warning("No se detectó código QR válido.")

# ------------------ Módulo: Consultar Asistencias ------------------
def modulo_consulta():
    st.header("📋 Consulta de Asistencias")
    conn = obtener_conexion()
    if conn:
        try:
            df = pd.read_sql("SELECT id, sesion_id, nombre, correo, hora_registro FROM asistencias ORDER BY hora_registro DESC", conn)
            if not df.empty:
                df['hora_registro'] = pd.to_datetime(df['hora_registro']).dt.strftime('%Y-%m-%d %H:%M:%S')
                st.dataframe(df)
            else:
                st.info("No hay asistencias registradas.")
        except Exception as e:
            st.error(f"Error al consultar: {e}")
        finally:
            conn.close()

# ------------------ Detección de QR ------------------
def detectar_qr(imagen_pil):
    try:
        detector = cv2.QRCodeDetector()
        imagen_cv = cv2.cvtColor(np.array(imagen_pil), cv2.COLOR_RGB2BGR)
        data, _, _ = detector.detectAndDecode(imagen_cv)
        return data if data else None
    except Exception as e:
        st.error(f"Error al detectar QR: {e}")
        return None

# ------------------ Aplicación Principal ------------------
def app():
    st.set_page_config(page_title="Sistema de Asistencia QR", layout="centered")
    if not st.session_state.get("autenticado"):
        login()
        return

    st.sidebar.title("📌 Menú")
    opciones = ["Registrar Asistencia", "Generar Código QR", "Consultar Asistencias", "Cerrar Sesión"]
    seleccion = st.sidebar.radio("Selecciona una opción:", opciones)

    if seleccion == "Registrar Asistencia":
        modulo_registro()
    elif seleccion == "Generar Código QR":
        modulo_generar_qr()
    elif seleccion == "Consultar Asistencias":
        modulo_consulta()
    elif seleccion == "Cerrar Sesión":
        st.session_state["autenticado"] = False
        st.experimental_rerun()

    st.sidebar.markdown("---")
    st.sidebar.info(f"Sesión iniciada como: {st.session_state.get('usuario')}")

# ------------------ Ejecutar ------------------
if __name__ == "__main__":
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
    app()
