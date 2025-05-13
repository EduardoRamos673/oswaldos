import streamlit as st
import psycopg2
import pandas as pd
import qrcode
import os
import cv2
import numpy as np
from PIL import Image
from datetime import datetime, timezone
import jwt

# --- Configuración ---
# Obtener la URL completa de la base de datos desde una variable de entorno
# Esta es la forma que usas en tu ejemplo, pero obteniéndola del entorno
DATABASE_URL_ENV = os.environ.get("postgresql://postgres.lqdsgwoeszsbqtlasxvt:Ramos1298@@aws-0-us-east-2.pooler.supabase.com:6543/postgres")
JWT_SECRET_KEY_ENV = os.environ.get("JWT_SECRET_KEY")

# --- Conexión con la base de datos (similar a tu ejemplo) ---
def obtener_conexion():
    if not DATABASE_URL_ENV:
        st.error("La variable de entorno 'DATABASE_URL' no está configurada. "
                 "Por favor, configúrala con la cadena de conexión a tu base de datos Supabase.")
        return None
    try:
        return psycopg2.connect(DATABASE_URL_ENV)
    except Exception as err:
        st.error(f"No se pudo conectar a la base de datos: {err}")
        st.error(f"Verifica que la variable de entorno 'DATABASE_URL' sea correcta.")
        return None

# --- Lógica de Código QR y Token ---
def crear_codigo_qr(id_sesion):
    if not JWT_SECRET_KEY_ENV:
        st.error("La variable de entorno 'JWT_SECRET_KEY' no está configurada. No se puede generar el token QR de forma segura.")
        return None, None

    os.makedirs("codigos_qr", exist_ok=True)
    payload = {
        "id_sesion": id_sesion,
        "hora_generacion": datetime.now(timezone.utc).isoformat()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY_ENV, algorithm="HS256")
    imagen_qr = qrcode.make(token)
    qr_path = f"codigos_qr/{id_sesion}.png"
    imagen_qr.save(qr_path)
    return token, qr_path


def decodificar_token(token_qr):
    if not JWT_SECRET_KEY_ENV:
        st.error("La variable de entorno 'JWT_SECRET_KEY' no está configurada. La validación del token no es confiable.")
        return None # O manejar el error de forma diferente
    try:
        return jwt.decode(token_qr, JWT_SECRET_KEY_ENV, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        st.error("El código QR ha expirado.")
        return None
    except jwt.InvalidTokenError:
        st.error("El código QR no es válido o está malformado.")
        return None
    except Exception as e:
        st.error(f"Error al decodificar el token: {e}")
        return None

# --- Módulos de Streamlit ---
def modulo_generar_qr():
    st.header("Creación de QR para la Asistencia")
    id_sesion = st.text_input("Ingrese el ID de la sesión (ej: MAT101-2023-S2-CLASE05)")
    if not id_sesion:
        st.info("Por favor, ingrese un ID de sesión para generar el código QR.")
        return

    if st.button("Crear QR"):
        if not id_sesion.strip():
            st.warning("El ID de la sesión no puede estar vacío.")
            return

        if not JWT_SECRET_KEY_ENV:
            st.error("No se puede generar el QR: La variable de entorno 'JWT_SECRET_KEY' no está configurada.")
            return

        token, qr_path = crear_codigo_qr(id_sesion)
        if token and qr_path:
            st.image(qr_path, caption=f"QR generado para la sesión: {id_sesion}")
            st.code(token)
            st.success(f"Código QR guardado como {qr_path}. (Nota: Este archivo puede ser temporal en algunos entornos de despliegue).")
        # El error de JWT_SECRET_KEY ya se maneja en crear_codigo_qr

def modulo_registro():
    st.header("Registro de Asistencia")
    nombre_usuario = st.text_input("Nombre completo")
    correo_usuario = st.text_input("Correo electrónico")

    st.subheader("Escanear código QR con la cámara")
    imagen_subida = st.camera_input("Apunta la cámara al código QR para capturarlo")

    if imagen_subida:
        if not nombre_usuario or not correo_usuario:
            st.warning("Por favor, ingrese su nombre y correo electrónico antes de escanear el QR.")
            return

        imagen_pil = Image.open(imagen_subida)
        contenido_qr = detectar_qr(imagen_pil)

        if contenido_qr:
            st.success("Código QR leído correctamente.")

            if not JWT_SECRET_KEY_ENV:
                st.error("No se puede validar el QR: La variable de entorno 'JWT_SECRET_KEY' no está configurada.")
                return

            info_token = decodificar_token(contenido_qr)

            if info_token:
                id_sesion_leido = info_token.get("id_sesion")
                hora_generacion_qr = info_token.get("hora_generacion")
                st.write(f"ID de Sesión del QR: {id_sesion_leido}")
                st.write(f"QR generado el (UTC): {hora_generacion_qr}")

                conn = obtener_conexion()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO asistencias (sesion_id, nombre, correo, hora_registro)
                                VALUES (%s, %s, %s, %s)
                            """, (id_sesion_leido, nombre_usuario, correo_usuario, datetime.now(timezone.utc)))
                            conn.commit()
                            st.success(f"Asistencia para '{nombre_usuario}' en la sesión '{id_sesion_leido}' guardada correctamente.")
                    except psycopg2.Error as db_err:
                        st.error(f"Error al guardar en la base de datos: {db_err}")
                        conn.rollback()
                    finally:
                        conn.close()
            # 'decodificar_token' ya muestra errores si el token no es válido
        else:
            st.warning("No se pudo leer ningún código QR en la imagen. Intente de nuevo enfocando mejor.")


def modulo_consulta():
    st.header("Lista de Asistencias Registradas")
    conn = obtener_conexion()
    if conn:
        try:
            consulta_sql = "SELECT id, sesion_id, nombre, correo, hora_registro FROM asistencias ORDER BY hora_registro DESC"
            data = pd.read_sql(consulta_sql, conn)

            if not data.empty:
                if 'hora_registro' in data.columns:
                    data['hora_registro'] = pd.to_datetime(data['hora_registro']).dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                st.dataframe(data)
            else:
                st.info("No se han registrado asistencias aún.")
        except pd.io.sql.DatabaseError as pd_err:
            st.error(f"Error al consultar la base de datos: {pd_err}")
            if "relation \"asistencias\" does not exist" in str(pd_err).lower():
                st.warning("La tabla 'asistencias' no existe en la base de datos. ¿La has creado según las instrucciones?")
        except Exception as e:
            st.error(f"Ocurrió un error inesperado al consultar asistencias: {e}")
        finally:
            conn.close()

# --- Función para detectar QR ---
def detectar_qr(imagen_pil):
    """Detecta y decodifica un código QR de una imagen PIL."""
    try:
        detector = cv2.QRCodeDetector()
        imagen_cv = cv2.cvtColor(np.array(imagen_pil), cv2.COLOR_RGB2BGR)
        data, _, _ = detector.detectAndDecode(imagen_cv)
        return data if data else None
    except Exception as e:
        st.error(f"Error durante la detección del QR: {e}")
        return None

# --- Aplicación Principal ---
def app():
    st.set_page_config(page_title="Sistema de Asistencia QR", layout="wide")
    st.title("🚀 Sistema de Registro de Asistencia con QR (Conexión por Variable de Entorno)")

    # Comprobación inicial de configuración
    if not DATABASE_URL_ENV or not JWT_SECRET_KEY_ENV:
        st.sidebar.error("⚠️ CONFIGURACIÓN INCOMPLETA ⚠️")
        st.sidebar.warning("La aplicación podría no funcionar correctamente. "
                           "Asegúrate de que las variables de entorno 'DATABASE_URL' y 'JWT_SECRET_KEY' estén configuradas.")

    st.sidebar.header("Navegación")
    secciones = ["Registrar Asistencia", "Generar Código QR", "Consultar Asistencias"]
    eleccion = st.sidebar.selectbox("Selecciona una opción:", secciones)

    if eleccion == "Registrar Asistencia":
        modulo_registro()
    elif eleccion == "Generar Código QR":
        modulo_generar_qr()
    elif eleccion == "Consultar Asistencias":
        modulo_consulta()

    st.sidebar.markdown("---")
    st.sidebar.info("Desarrollado con Streamlit y Supabase.")

if __name__ == "__main__":
    app()