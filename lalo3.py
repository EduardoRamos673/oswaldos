import streamlit as st
import sqlite3
import pandas as pd
import qrcode
import os
import cv2
import numpy as np
from PIL import Image
from datetime import datetime

# --- Conexión con la base de datos SQLite ---
def obtener_conexion():
    try:
        return sqlite3.connect('data/database.db')
    except Exception as err:
        st.error(f"No se pudo conectar a la base de datos SQLite: {err}")
        return None

# --- Crear código QR ---
def crear_codigo_qr_simple(id_sesion):
    os.makedirs("codigos_qr", exist_ok=True)
    imagen_qr = qrcode.make(id_sesion)
    qr_path = f"codigos_qr/sesion_{id_sesion}.png"
    try:
        imagen_qr.save(qr_path)
        return qr_path
    except Exception as e:
        st.error(f"Error al guardar la imagen QR: {e}")
        return None

# --- Registrar asistencia ---
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
        id_sesion_leido = detectar_qr(imagen_pil)

        if id_sesion_leido:
            st.success(f"Código QR leído. ID de Sesión detectado: {id_sesion_leido}")

            conn = obtener_conexion()
            if conn:
                try:
                    cur = conn.cursor()

                    # Insertar la sesión si no existe (opcional)
                    cur.execute("SELECT id FROM clases WHERE qr_token = ?", (id_sesion_leido,))
                    clase = cur.fetchone()

                    if not clase:
                        st.error(f"No existe ninguna clase con QR token '{id_sesion_leido}'.")
                        return

                    clase_id = clase[0]

                    # Insertar usuario si no existe
                    cur.execute("SELECT id FROM usuarios WHERE correo = ?", (correo_usuario,))
                    estudiante = cur.fetchone()
                    if not estudiante:
                        cur.execute("INSERT INTO usuarios (username, password, nombre, tipo, correo) VALUES (?, ?, ?, ?, ?)",
                                    (correo_usuario, "1234", nombre_usuario, "alumno", correo_usuario))
                        conn.commit()
                        estudiante_id = cur.lastrowid
                    else:
                        estudiante_id = estudiante[0]

                    # Insertar asistencia
                    cur.execute("""
                        INSERT INTO asistencias (estudiante_id, clase_id, fecha)
                        VALUES (?, ?, ?)
                    """, (estudiante_id, clase_id, datetime.now()))
                    conn.commit()
                    st.success(f"Asistencia para '{nombre_usuario}' registrada correctamente.")
                except sqlite3.Error as db_err:
                    conn.rollback()
                    st.error(f"Error en la base de datos: {db_err}")
                finally:
                    conn.close()
        else:
            st.warning("No se pudo leer ningún código QR. Intente nuevamente.")

# --- Generar QR ---
def modulo_generar_qr():
    st.header("Creación de QR para la Asistencia (Simple)")
    id_sesion = st.text_input("Ingrese el ID de la sesión (ej: MAT101-2023-S2-CLASE05)")

    if not id_sesion:
        st.info("Por favor, ingrese un ID de sesión para generar el código QR.")
        return

    if st.button("Crear QR"):
        conn = obtener_conexion()
        if conn:
            try:
                cur = conn.cursor()

                # Crear clase si no existe
                cur.execute("SELECT id FROM clases WHERE qr_token = ?", (id_sesion,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO clases (nombre, profesor_id, qr_token) VALUES (?, ?, ?)",
                                (id_sesion, 1, id_sesion))  # profesor_id=1 por defecto (admin)
                    conn.commit()

                qr_path = crear_codigo_qr_simple(id_sesion)
                if qr_path:
                    st.image(qr_path, caption=f"QR generado para la sesión: {id_sesion}")
                    st.success(f"Código QR guardado como {qr_path}. El QR contiene: '{id_sesion}'")
                else:
                    st.error("No se pudo generar el código QR.")
            except Exception as e:
                st.error(f"Error al guardar clase en la base de datos: {e}")
            finally:
                conn.close()

# --- Consultar asistencias ---
def modulo_consulta():
    st.header("Lista de Asistencias Registradas")
    conn = obtener_conexion()
    if conn:
        try:
            data = pd.read_sql_query("""
                SELECT a.id, u.nombre, u.correo, c.nombre as clase, a.fecha
                FROM asistencias a
                JOIN usuarios u ON a.estudiante_id = u.id
                JOIN clases c ON a.clase_id = c.id
                ORDER BY a.fecha DESC
            """, conn)
            if not data.empty:
                st.dataframe(data)
            else:
                st.info("No se han registrado asistencias aún.")
        except Exception as e:
            st.error(f"Error al consultar la base de datos: {e}")
        finally:
            conn.close()

# --- Detección de QR ---
def detectar_qr(imagen_pil):
    try:
        detector = cv2.QRCodeDetector()
        imagen_cv = cv2.cvtColor(np.array(imagen_pil), cv2.COLOR_RGB2BGR)
        data, _, _ = detector.detectAndDecode(imagen_cv)
        return data if data else None
    except Exception as e:
        st.error(f"Error durante la detección del QR: {e}")
        return None

# --- App principal ---
def app():
    st.set_page_config(page_title="Sistema de Asistencia QR (SQLite)", layout="wide")
    st.title("📲 Sistema de Registro de Asistencia con QR (SQLite)")

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
    st.sidebar.info("Versión con base de datos SQLite local.")

if __name__ == "__main__":
    app()
