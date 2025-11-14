#!/usr/bin/env python3
# bot.py - Rekber Bot (Aiogram v2.25.1)
# Requirements: aiogram==2.25.1

import os
import logging
import sqlite3
import re
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

# ---------------- CONFIG ----------------
# Put TOKEN, ADMIN_ID, CHANNEL, BOT_ID in config.py or environment variables
TOKEN = "8377959008:AAF9Qw9qA0jEsx5eHdCWAxFeW3JRryFs2SI"
ADMIN_ID =  8163114928
CHANNEL = "@rekberdavinn"
BOT_ID = 8377959008

if not TOKEN or not ADMIN_ID:
    print("ERROR: Set TOKEN and ADMIN_ID in environment or config.py")
    exit(1)

DB_PATH = "rekber.db"
PROOFS_DIR = "proofs"
os.makedirs(PROOFS_DIR, exist_ok=True)

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ---------------- Messages ----------------
FORMAT_REKBER = (
"```\n"
"━ • ⓘ ❲ FORMAT REKBER ❳\n\n"
"format : \n"
"─ ⭑ Username seller :\n"
"─ ⭑ Username buyer :\n"
"─ ⭑ Jenis barang :\n"
"─ ⭑ Harga :\n"
"─ ⭑ Reff / NoReff :\n\n"
"Silahkan isi format rekber untuk melakukan transaksi\n"
"dan kirim ulang format yang telah diisi.\n"
"Admin akan melakukan pengecekan dan persetujuan.\n"
"```"
)

PAY_NOTICE = "SILAHKAN KIRIM BUKTI TRANSFER YA KAKA🙏"
MASUK_MESSAGE = (
"📌 dana sudah aman ya kaka , silahkan baca format di bawah\n\n"
"Tahap Selanjutnya :\n"
"- Penjual kirim akun/item ke Pembeli\n"
"- Kalo udah Aman, Pembeli Konfirmasi DONE disini,Agar dana dicairkan ke penjual\n\n"
"PERATURAN TRANSAKSI ‼️\n"
"⚠️Waktu Transaksi dihitung Setelah Penjual Memberi data , Jika pembeli tidak ada Respon Selama 1 Jam , Dana Saya Cairkan Ke penjual ‼️"
)
DONE_MESSAGE = (
"ALHAMDULILLAH \n🔰TERIMA KASIH🔰\n"
"__________________\n"
"Dana Sudah Dikirim Ya\n"
"Silahkan Cek Mutasi Rekening/E-Wallet Anda\n"
"Selamat Ber-Transaksi Kembali Arigaato🔥"
)

# ---------------- DB HELPERS ----------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_seen TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS banned_users (
        id INTEGER PRIMARY KEY,
        reason TEXT,
        banned_at TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payment_methods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,
        label TEXT,
        details TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id TEXT PRIMARY KEY,
        buyer_username TEXT,
        seller_username TEXT,
        item TEXT,
        price TEXT,
        reff TEXT,
        status TEXT,
        created_at TEXT,
        admin_id INTEGER,
        group_chat_id INTEGER,
        proof_file TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        action TEXT,
        info TEXT
    )""")
    con.commit()
    con.close()

def db_execute(query, params=(), fetch=False, many=False):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    if many:
        cur.executemany(query, params)
        con.commit()
        con.close()
        return
    cur.execute(query, params)
    if fetch:
        rows = cur.fetchall()
        con.close()
        return rows
    con.commit()
    con.close()

# user helpers
def add_user_if_not_exists(user_id:int, username:Optional[str]):
    now = datetime.utcnow().isoformat()
    rows = db_execute("SELECT id FROM users WHERE id=?", (user_id,), fetch=True)
    if not rows:
        db_execute("INSERT INTO users (id, username, first_seen) VALUES (?, ?, ?)", (user_id, username, now))

def all_user_ids():
    rows = db_execute("SELECT id FROM users", fetch=True)
    return [r[0] for r in rows]

# admins
def ensure_admin_exists(admin_id):
    rows = db_execute("SELECT id FROM admins WHERE id=?", (admin_id,), fetch=True)
    if not rows:
        db_execute("INSERT INTO admins (id) VALUES (?)", (admin_id,))

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    rows = db_execute("SELECT id FROM admins WHERE id=?", (user_id,), fetch=True)
    return bool(rows)

def add_admin(user_id):
    ensure_admin_exists(user_id)

def remove_admin(user_id):
    db_execute("DELETE FROM admins WHERE id=?", (user_id,))

# banned
def ban_user(user_id:int, reason:str=""):
    now = datetime.utcnow().isoformat()
    db_execute("INSERT OR REPLACE INTO banned_users (id, reason, banned_at) VALUES (?, ?, ?)", (user_id, reason, now))

def unban_user(user_id:int):
    db_execute("DELETE FROM banned_users WHERE id=?", (user_id,))

def is_banned(user_id:int):
    rows = db_execute("SELECT id FROM banned_users WHERE id=?", (user_id,), fetch=True)
    return bool(rows)

# payment
def add_payment_method(kind, label, details):
    db_execute("INSERT INTO payment_methods (kind, label, details) VALUES (?, ?, ?)", (kind, label, details))

def remove_payment_method(pm_id):
    db_execute("DELETE FROM payment_methods WHERE id=?", (pm_id,))

def list_payment_methods():
    rows = db_execute("SELECT id, kind, label, details FROM payment_methods", fetch=True)
    return rows

# transactions
def create_transaction(tx_id, buyer, seller, item, price, reff, admin_id):
    now = datetime.utcnow().isoformat()
    db_execute("INSERT INTO transactions (tx_id, buyer_username, seller_username, item, price, reff, status, created_at, admin_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (tx_id, buyer, seller, item, price, reff, "pending", now, admin_id))

def set_transaction_group(tx_id, chat_id):
    db_execute("UPDATE transactions SET group_chat_id=?, status='grouped' WHERE tx_id=?", (chat_id, tx_id))

def set_transaction_status(tx_id, status, proof_file=None):
    if proof_file:
        db_execute("UPDATE transactions SET status=?, proof_file=? WHERE tx_id=?", (status, proof_file, tx_id))
    else:
        db_execute("UPDATE transactions SET status=? WHERE tx_id=?", (status, tx_id))

def get_transaction(tx_id):
    rows = db_execute("SELECT tx_id, buyer_username, seller_username, item, price, reff, status, admin_id, group_chat_id, proof_file FROM transactions WHERE tx_id=?", (tx_id,), fetch=True)
    return rows[0] if rows else None

def log_action(action, info=""):
    now = datetime.utcnow().isoformat()
    db_execute("INSERT INTO logs (ts, action, info) VALUES (?, ?, ?)", (now, action, info))

# ---------------- Utilities ----------------
def parse_format_text(text: str):
    def get_field(label):
        m = re.search(rf"{re.escape(label)}\s*:\s*(.+)", text, re.IGNORECASE)
        return m.group(1).strip() if m else ""
    seller = get_field("Username seller")
    buyer = get_field("Username buyer")
    item = get_field("Jenis barang")
    price = get_field("Harga")
    reff = get_field("Reff") or get_field("NoReff") or get_field("Reff / NoReff")
    return seller, buyer, item, price, reff

def gen_tx_id():
    return "RKB" + datetime.utcnow().strftime("%Y%m%d%H%M%S")

# ---------------- Force Join Channel ----------------
async def is_joined_channel(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in ("member", "creator", "administrator")
    except Exception:
        return False

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join_callback(cb: types.CallbackQuery):
    joined = await is_joined_channel(cb.from_user.id)
    if joined:
        await cb.message.edit_text("✔️ Terima kasih, kamu sudah join channel.\nSilakan gunakan bot sekarang.")
        await cb.answer()
    else:
        await cb.answer("❌ Kamu belum join!", show_alert=True)

# This handler will intercept messages (except /start) and enforce join
@dp.message_handler(lambda m: m.text and not m.text.startswith("/start") and not m.text.startswith("/adminpanel"))
async def force_join_filter(message: types.Message):
    # Admins bypass force join
    if is_admin(message.from_user.id):
        return  # allow admin use without joining
    joined = await is_joined_channel(message.from_user.id)
    if not joined:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 JOIN CHANNEL", url=f"https://t.me/{CHANNEL.replace('@','')}"))
        kb.add(InlineKeyboardButton("✔️ Check Again", callback_data="check_join"))
        try:
            await message.reply(
                "🚫 Kamu harus join channel terlebih dahulu sebelum menggunakan bot.\n\nKlik tombol di bawah:",
                reply_markup=kb
            )
        except Exception:
            pass
        return

# ---------------- Handlers ----------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user = message.from_user
    add_user_if_not_exists(user.id, user.username)
    if is_banned(user.id):
        await message.reply("Anda diblokir dari bot ini.")
        return
    # check channel membership
    try:
        member = await bot.get_chat_member(CHANNEL, user.id)
        joined = member.status in ("member", "creator", "administrator")
    except Exception:
        joined = False
    if not joined:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📢 JOIN CHANNEL", url=f"https://t.me/{CHANNEL.replace('@','')}"))
        kb.add(InlineKeyboardButton("✔️ Check Again", callback_data="check_join"))
        await message.reply("Silahkan join channel terlebih dahulu\n\nCHANNEL ( MENU INLINE BUTTON )", reply_markup=kb)
        return
    await message.reply("Halo! Selamat datang di Rekber Bot.\nGunakan /format untuk membuat transaksi rekber.\nJika kamu admin, ketik /adminpanel untuk membuka panel admin.")

@dp.message_handler(commands=["format"])
async def cmd_format(message: types.Message):
    user = message.from_user
    add_user_if_not_exists(user.id, user.username)
    if is_banned(user.id):
        await message.reply("Anda diblokir dari bot ini.")
        return
    await message.reply(FORMAT_REKBER, parse_mode="Markdown")

@dp.message_handler(lambda m: isinstance(m.text, str) and "Username seller" in m.text and "Username buyer" in m.text)
async def handle_format_submission(message: types.Message):
    user = message.from_user
    add_user_if_not_exists(user.id, user.username)
    if is_banned(user.id):
        return
    # ensure joined (admins bypass earlier)
    if not is_admin(user.id):
        joined = await is_joined_channel(user.id)
        if not joined:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("📢 JOIN CHANNEL", url=f"https://t.me/{CHANNEL.replace('@','')}"))
            kb.add(InlineKeyboardButton("✔️ Check Again", callback_data="check_join"))
            await message.reply("Silahkan join channel terlebih dahulu sebelum mengirim format.", reply_markup=kb)
            return

    text = message.text
    seller, buyer, item, price, reff = parse_format_text(text)
    if not seller or not buyer:
        await message.reply("Format kurang lengkap. Pastikan mengisi Username seller dan Username buyer.")
        return
    tx_id = gen_tx_id()
    create_transaction(tx_id, buyer, seller, item, price, reff, ADMIN_ID)
    log_action("new_request", f"{tx_id} by {user.id}")
    admin_msg = (f"🆕 Permintaan REKBER\nTX: {tx_id}\n\n{text}\n\n"
                 f"✅ Approve: /approve_{tx_id}\n❌ Reject: /reject_{tx_id}\n\n"
                 f"Setelah approve: buat grup, tambahkan bot + buyer + seller lalu jalankan di grup:\n/link_group {tx_id}")
    try:
        await bot.send_message(ADMIN_ID, admin_msg)
    except Exception:
        log.exception("gagal kirim notifikasi ke admin")
    await message.reply(f"Terima kasih! Permintaanmu diteruskan ke admin.\nID Transaksi: {tx_id}")

@dp.message_handler(regexp=r"^/approve_RKB\d+")
async def approve_handler(message: types.Message):
    user = message.from_user
    if not is_admin(user.id):
        return
    m = re.match(r"^/approve_(RKB\d+)", message.text.strip())
    if not m:
        return
    tx_id = m.group(1)
    tx = get_transaction(tx_id)
    if not tx:
        await message.reply("Transaksi tidak ditemukan.")
        return
    set_transaction_status(tx_id, "approved")
    log_action("approve", tx_id)
    instr = (f"Transaksi {tx_id} disetujui.\n\n"
             "Langkah selanjutnya:\n1. Buat grup baru (contoh nama: REKBER buyer x seller)\n2. Tambahkan bot ini, buyer, dan seller ke grup\n"
             f"3. Di dalam grup jalankan:\n/link_group {tx_id}\n\nSetelah group di-link, admin dapat memakai perintah: .pay .masuk .done")
    await message.reply(instr)

@dp.message_handler(regexp=r"^/reject_RKB\d+")
async def reject_handler(message: types.Message):
    user = message.from_user
    if not is_admin(user.id):
        return
    m = re.match(r"^/reject_(RKB\d+)", message.text.strip())
    if not m:
        return
    tx_id = m.group(1)
    tx = get_transaction(tx_id)
    if not tx:
        await message.reply("Transaksi tidak ditemukan.")
        return
    set_transaction_status(tx_id, "rejected")
    log_action("reject", tx_id)
    await message.reply(f"Transaksi {tx_id} telah ditolak.")

@dp.message_handler(commands=["link_group"])
async def link_group_handler(message: types.Message):
    chat = message.chat
    user = message.from_user
    if chat.type == "private":
        await message.reply("Perintah ini harus dijalankan di dalam grup yang ingin di-link.")
        return
    if not is_admin(user.id):
        # check group admin
        try:
            mem = await bot.get_chat_member(chat.id, user.id)
            if mem.status not in ("creator", "administrator"):
                await message.reply("Hanya admin bot atau admin grup yang bisa melakukan ini.")
                return
        except Exception:
            await message.reply("Tidak bisa memeriksa admin grup.")
            return
    args = message.get_args().split()
    if not args:
        await message.reply("Gunakan: /link_group <TX_ID>")
        return
    tx_id = args[0].strip()
    tx = get_transaction(tx_id)
    if not tx:
        await message.reply("Transaksi tidak ditemukan.")
        return
    set_transaction_group(tx_id, chat.id)
    log_action("link_group", f"{tx_id} -> {chat.id}")
    await message.reply(f"Transaksi {tx_id} berhasil di-link ke grup ini. Perintah .pay .masuk .done sekarang aktif di grup.")

# group commands .pay .masuk .done (must be message starting with dot)
@dp.message_handler(lambda m: isinstance(m.text, str) and m.text.strip().startswith("."))
async def group_dot_commands(message: types.Message):
    chat = message.chat
    user = message.from_user
    text = message.text.strip()
    if chat.type == "private":
        return
    if is_banned(user.id):
        return
    # check admin rights
    allowed = is_admin(user.id)
    if not allowed:
        try:
            mem = await bot.get_chat_member(chat.id, user.id)
            allowed = mem.status in ("creator", "administrator")
        except Exception:
            allowed = False
    if not allowed:
        return
    if text.startswith(".pay"):
        rows = list_payment_methods()
        if not rows:
            await message.reply("Belum ada metode pembayaran terdaftar. Admin: buka /adminpanel -> Kelola Payment.")
            return
        out = "⏬ Metode Pembayaran ⏬\n\n"
        banks = [r for r in rows if r[1]=="bank"]
        ew = [r for r in rows if r[1]=="ewallet"]
        if banks:
            out += "BANK:\n" + "\n".join([f"- {r[2]} : {r[3]}" for r in banks]) + "\n"
        if ew:
            out += "\nEWALLET:\n" + "\n".join([f"- {r[2]} : {r[3]}" for r in ew]) + "\n"
        out += f"\n{PAY_NOTICE}"
        await message.reply(out)
    elif text.startswith(".masuk"):
        await message.reply(MASUK_MESSAGE)
    elif text.startswith(".done"):
        # find proof in message or reply
        file_path = None
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = await bot.get_file(file_id)
            file_path = os.path.join(PROOFS_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file_id}.jpg")
            await file_info.download(file_path)
        elif message.document:
            file_id = message.document.file_id
            fname = message.document.file_name or f"{file_id}"
            file_info = await bot.get_file(file_id)
            file_path = os.path.join(PROOFS_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{fname}")
            await file_info.download(file_path)
        elif message.reply_to_message:
            rm = message.reply_to_message
            if rm.photo:
                file_id = rm.photo[-1].file_id
                file_info = await bot.get_file(file_id)
                file_path = os.path.join(PROOFS_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file_id}.jpg")
                await file_info.download(file_path)
            elif rm.document:
                file_id = rm.document.file_id
                fname = rm.document.file_name or f"{file_id}"
                file_info = await bot.get_file(file_id)
                file_path = os.path.join(PROOFS_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{fname}")
                await file_info.download(file_path)
        # link to tx
        rows = db_execute("SELECT tx_id FROM transactions WHERE group_chat_id=?", (chat.id,), fetch=True)
        tx_id = rows[0][0] if rows else None
        if not tx_id:
            await message.reply("Tidak ada transaksi yang terkait dengan grup ini.")
            return
        if not file_path:
            await message.reply("Silakan sertakan bukti transfer (foto/file) bersama .done atau balas pesan bukti dengan .done")
            return
        set_transaction_status(tx_id, "done", proof_file=file_path)
        log_action("done", tx_id)
        await message.reply(DONE_MESSAGE)
        # send proof preview
        try:
            await bot.send_document(chat.id, InputFile(file_path), caption=f"Bukti transfer untuk {tx_id}")
        except Exception:
            pass

# Admin panel with inline buttons
@dp.message_handler(commands=["adminpanel"])
async def adminpanel_cmd(message: types.Message):
    user = message.from_user
    if not is_admin(user.id):
        await message.reply("Kamu bukan admin.")
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📄 Kelola Payment", callback_data="pm_menu"),
        InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
        InlineKeyboardButton("🚫 Ban User", callback_data="ban_menu"),
        InlineKeyboardButton("✅ Unban User", callback_data="unban_menu"),
        InlineKeyboardButton("👥 List User", callback_data="user_list"),
        InlineKeyboardButton("➕ Tambah Admin", callback_data="add_admin"),
        InlineKeyboardButton("➖ Hapus Admin", callback_data="remove_admin"),
        InlineKeyboardButton("❌ Tutup", callback_data="close_admin")
    )
    await message.reply("🛠 Admin Panel\nSilahkan pilih menu:", reply_markup=kb)

@dp.callback_query_handler(lambda c: True)
async def callback_handler(cb: types.CallbackQuery):
    user = cb.from_user
    if not is_admin(user.id):
        await cb.answer("Bukan admin", show_alert=True)
        return
    data = cb.data
    # Payment menu
    if data == "pm_menu":
        rows = list_payment_methods()
        text = "📄 KELOLA PAYMENT\n\n"
        if not rows:
            text += "Belum ada metode pembayaran.\n"
        else:
            for r in rows:
                text += f"ID:{r[0]} | {r[1]} | {r[2]} : {r[3]}\n"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Tambah Bank", callback_data="pm_add_bank"),
               InlineKeyboardButton("➕ Tambah E-Wallet", callback_data="pm_add_ewallet"),
               InlineKeyboardButton("🗑 Hapus Metode", callback_data="pm_del"),
               InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back"))
        await cb.message.edit_text(text, reply_markup=kb)
    elif data == "pm_add_bank":
        await cb.message.edit_text("Kirim data bank dengan format:\nBankName - account_number - a/n Name")
        await cb.answer()
        set_state(user.id, "awaiting_pm_bank")
    elif data == "pm_add_ewallet":
        await cb.message.edit_text("Kirim data e-wallet dengan format:\nDana - 08xxxx - a/n Name")
        await cb.answer()
        set_state(user.id, "awaiting_pm_ewallet")
    elif data == "pm_del":
        rows = list_payment_methods()
        if not rows:
            await cb.message.edit_text("Tidak ada metode pembayaran untuk dihapus.", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="pm_menu")))
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for r in rows:
            kb.add(InlineKeyboardButton(f"❌ {r[0]} {r[1]} {r[2]}", callback_data=f"pm_remove_{r[0]}"))
        kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="pm_menu"))
        await cb.message.edit_text("Pilih metode yang ingin dihapus:", reply_markup=kb)
    elif data and data.startswith("pm_remove_"):
        pm_id = int(data.split("_")[-1])
        remove_payment_method(pm_id)
        await cb.message.edit_text("Metode dihapus.", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="pm_menu")))
    # broadcast
    elif data == "broadcast_menu":
        await cb.message.edit_text("Kirim pesan untuk broadcast sekarang (text atau reply with media).")
        await cb.answer()
        set_state(user.id, "awaiting_broadcast")
    # ban/unban
    elif data == "ban_menu":
        await cb.message.edit_text("Kirim user_id untuk diban.")
        await cb.answer()
        set_state(user.id, "awaiting_ban")
    elif data == "unban_menu":
        await cb.message.edit_text("Kirim user_id untuk diunban.")
        await cb.answer()
        set_state(user.id, "awaiting_unban")
    elif data == "user_list":
        uids = all_user_ids()
        text = f"👥 Total user: {len(uids)}\n\n" + "\n".join([str(u) for u in uids[:200]])
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")))
    elif data == "add_admin":
        await cb.message.edit_text("Kirim user_id untuk ditambahkan sebagai admin.")
        await cb.answer()
        set_state(user.id, "awaiting_add_admin")
    elif data == "remove_admin":
        await cb.message.edit_text("Kirim user_id untuk dihapus dari admin.")
        await cb.answer()
        set_state(user.id, "awaiting_remove_admin")
    elif data == "admin_back":
        await adminpanel_cmd(cb.message)
    elif data == "close_admin":
        await cb.message.edit_text("Admin panel ditutup.")
    else:
        await cb.answer()

# Simple in-memory state
user_states = {}  # dict: user_id -> state string

def set_state(user_id, state):
    user_states[user_id] = state

def get_state(user_id):
    return user_states.get(user_id)

def clear_state(user_id):
    if user_id in user_states: user_states.pop(user_id, None)

@dp.message_handler(lambda m: True, content_types=types.ContentTypes.ANY)
async def generic_handler(message: types.Message):
    user = message.from_user
    add_user_if_not_exists(user.id, user.username)

    state = get_state(user.id)
    text = (message.text or "").strip()

    # awaiting pm bank/ewallet
    if state == "awaiting_pm_bank" and is_admin(user.id):
        parts = [p.strip() for p in text.split("-",1)] if text else [text, text]
        label = parts[0] if parts else text
        details = parts[1] if len(parts)>1 else text
        add_payment_method("bank", label, details)
        await message.reply(f"✔ Bank ditambahkan: {label} - {details}")
        clear_state(user.id)
        return
    if state == "awaiting_pm_ewallet" and is_admin(user.id):
        parts = [p.strip() for p in text.split("-",1)] if text else [text, text]
        label = parts[0] if parts else text
        details = parts[1] if len(parts)>1 else text
        add_payment_method("ewallet", label, details)
        await message.reply(f"✔ E-Wallet ditambahkan: {label} - {details}")
        clear_state(user.id)
        return

    if state == "awaiting_broadcast" and is_admin(user.id):
        uids = all_user_ids()
        count = 0
        if message.photo:
            fid = message.photo[-1].file_id
            caption = message.caption or text
            for uid in uids:
                try:
                    await bot.send_photo(uid, fid, caption=caption)
                    count += 1
                except: pass
        elif message.document:
            fid = message.document.file_id
            caption = message.caption or text
            for uid in uids:
                try:
                    await bot.send_document(uid, fid, caption=caption)
                    count += 1
                except: pass
        else:
            for uid in uids:
                try:
                    await bot.send_message(uid, text)
                    count += 1
                except: pass
        await message.reply(f"Broadcast terkirim ke {count}/{len(uids)} user.")
        clear_state(user.id)
        return

    if state == "awaiting_ban" and is_admin(user.id):
        try:
            tid = int(text)
            ban_user(tid, reason="manual admin")
            await message.reply(f"User {tid} dibanned.")
        except:
            await message.reply("ID tidak valid.")
        clear_state(user.id)
        return

    if state == "awaiting_unban" and is_admin(user.id):
        try:
            tid = int(text)
            unban_user(tid)
            await message.reply(f"User {tid} diunban.")
        except:
            await message.reply("ID tidak valid.")
        clear_state(user.id)
        return

    if state == "awaiting_add_admin" and is_admin(user.id):
        try:
            tid = int(text)
            add_admin(tid)
            await message.reply(f"User {tid} ditambahkan sebagai admin.")
        except:
            await message.reply("ID tidak valid.")
        clear_state(user.id)
        return

    if state == "awaiting_remove_admin" and is_admin(user.id):
        try:
            tid = int(text)
            remove_admin(tid)
            await message.reply(f"User {tid} dihapus dari admin.")
        except:
            await message.reply("ID tidak valid.")
        clear_state(user.id)
        return

    # no other action (fallback)
    return

# Admin helper to get proof file path
@dp.message_handler(commands=["get_proof"])
async def cmd_get_proof(message: types.Message):
    user = message.from_user
    if not is_admin(user.id):
        await message.reply("Kamu bukan admin.")
        return
    args = message.get_args().split()
    if not args:
        await message.reply("Gunakan: /get_proof <TX_ID>")
        return
    tx_id = args[0].strip()
    tx = get_transaction(tx_id)
    if not tx:
        await message.reply("Transaksi tidak ditemukan.")
        return
    proof = tx[9]  # proof_file field
    if not proof:
        await message.reply("Tidak ada bukti tersimpan untuk transaksi ini.")
        return
    try:
        await bot.send_document(message.chat.id, InputFile(proof), caption=f"Bukti untuk {tx_id}")
    except Exception:
        await message.reply("Gagal mengirim bukti (file mungkin tidak ada).")

# ---------------- Startup ----------------
def main():
    init_db()
    ensure_admin_exists(ADMIN_ID)
    log.info("Bot is starting (Aiogram)...")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
