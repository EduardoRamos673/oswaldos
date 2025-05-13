import streamlit as st
import psycopg2
import pandas as pd
import qrcode
import os
import cv2
import numpy as np
from PIL import Image
from datetime import datetime, timezone

# --- Configuración ---
# Obtener la URL completa de la base de datos desde una variable de entorno
DATABASE_URL_ENV = os.environ.get("postgresql://postgres.lqdsgwoeszsbqtlasxvt:Ramos1298%40@aws-0-us-east-2.pooler.supabase.com:6543/postgres")

# --- Conexión con la base de datos ---
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

# --- Lógica de Código QR (Ahora más simple) ---
def crear_codigo_qr_simple(id_sesion):
    """
    Crea un código QR que contiene directamente el id_sesion.
    """
    os.makedirs("codigos_qr", exist_ok=True)
    # El QR contendrá directamente el id_sesion
    imagen_qr = qrcode.make(id_sesion)
    qr_path = f"codigos_qr/sesion_{id_sesion}.png" # Modificado para evitar conflictos si id_sesion tiene caracteres especiales
    try:
        imagen_qr.save(qr_path)
        return qr_path
    except Exception as e:
        st.error(f"Error al guardar la imagen QR: {e}")
        return None

# --- Módulos de Streamlit ---
def modulo_generar_qr():
    st.header("Creación de QR para la Asistencia (Simple)")
    id_sesion = st.text_input("Ingrese el ID de la sesión (ej: MAT101-2023-S2-CLASE05)")
    if not id_sesion:
        st.info("Por favor, ingrese un ID de sesión para generar el código QR.")
        return

    if st.button("Crear QR"):
        if not id_sesion.strip():
            st.warning("El ID de la sesión no puede estar vacío.")
            return

        qr_path = crear_codigo_qr_simple(id_sesion)
        if qr_path:
            st.image(qr_path, caption=f"QR generado para la sesión: {id_sesion}")
            st.success(f"Código QR guardado como {qr_path}. El QR contiene: '{id_sesion}'")
        else:
            st.error("No se pudo generar el código QR.")


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
        id_sesion_leido = detectar_qr(imagen_pil) # detectar_qr ahora devuelve directamente el contenido del QR

        if id_sesion_leido:
            st.success(f"Código QR leído. ID de Sesión detectado: {id_sesion_leido}")

            conn = obtener_conexion()
            if conn:
                try:
                    with conn.cursor() as cur:
                        # Aquí podrías añadir una verificación si la sesión existe antes de insertar,
                        # pero por simplicidad, intentamos la inserción directamente.
                        # La base de datos podría tener una FK a una tabla de sesiones.
                        cur.execute("""
                            INSERT INTO asistencias (sesion_id, nombre, correo, hora_registro)
                            VALUES (%s, %s, %s, %s)
                        """, (id_sesion_leido, nombre_usuario, correo_usuario, datetime.now(timezone.utc)))
                        conn.commit()
                        st.success(f"Asistencia para '{nombre_usuario}' en la sesión '{id_sesion_leido}' guardada correctamente.")
                except psycopg2.IntegrityError as ie:
                    conn.rollback()
                    # Esto podría pasar si 'sesion_id' es una clave foránea y el ID no existe
                    # o si hay otra restricción de integridad.
                    st.error(f"Error de integridad al guardar en la base de datos: {ie}. ¿Existe la sesión '{id_sesion_leido}'?")
                except psycopg2.Error as db_err:
                    conn.rollback()
                    st.error(f"Error al guardar en la base de datos: {db_err}")
                finally:
                    conn.close()
            else:
                st.error("No se pudo establecer conexión con la base de datos para guardar la asistencia.")
        else:
            st.warning("No se pudo leer ningún código QR en la imagen o el QR está vacío. Intente de nuevo enfocando mejor.")


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
                st.warning("La tabla 'asistencias' no existe en la base de datos. ¿La has creado?")
        except Exception as e:
            st.error(f"Ocurrió un error inesperado al consultar asistencias: {e}")
        finally:
            conn.close()

# --- Función para detectar QR (devuelve el contenido directamente) ---
def detectar_qr(imagen_pil):
    """
    Detecta y decodifica un código QR de una imagen PIL.
    Devuelve el contenido del QR directamente.
    """
    try:
        detector = cv2.QRCodeDetector()
        imagen_cv = cv2.cvtColor(np.array(imagen_pil), cv2.COLOR_RGB2BGR)
        data, _, _ = detector.detectAndDecode(imagen_cv)
        return data if data else None # Retorna data (string) si se encontró, sino None
    except Exception as e:
        st.error(f"Error durante la detección del QR: {e}")
        return None

# --- Aplicación Principal ---
def app():
    st.set_page_config(page_title="Sistema de Asistencia QR (Simple)", layout="wide")
    st.title("📲 Sistema de Registro de Asistencia con QR (Versión Simple)")

    if not DATABASE_URL_ENV:
        st.sidebar.error("⚠️ CONFIGURACIÓN INCOMPLETA ⚠️")
        st.sidebar.warning("La aplicación no funcionará sin la variable de entorno 'DATABASE_URL'.")

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
    # Para desarrollo local con .env:
    # from dotenv import load_dotenv
    # load_dotenv()
    # DATABASE_URL_ENV = os.environ.get("DATABASE_URL") # Recargar después de load_dotenv si se define arriba
    app()