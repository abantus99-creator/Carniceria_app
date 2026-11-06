import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO

# ==================== BASE DE DATOS ====================
def get_db():
    conn = sqlite3.connect("carniceria.db")
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            categoria TEXT,
            precio REAL,
            stock REAL,
            minimo REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            cantidad REAL,
            total REAL,
            fecha TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
