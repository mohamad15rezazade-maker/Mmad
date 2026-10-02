# ==========================================
# 🎮 DAWGS TELEGRAM BOT - نسخه نهایی
# ==========================================

import asyncio
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

# ==================== CONFIG ====================
TOKEN = "توکن_بات_خودت_رو_اینجا_بذار"

OWNER_IDS = [8935601841, 8458210170]

CHANNEL_ID = -1001234567890
ALLOWED_GROUP_ID = -1001234567890
GROUP_LINK = "https://t.me/GAP_BAZIN1"

MIN_WITHDRAW = 2000
MIN_BET = 60
REFERRAL_REWARD = 60
MAX_THROWS = 3

GAME_EMOJI = {"tas": "🎲", "bowling": "🎳", "basketball": "🏀", "dart": "🎯"}
GAME_NAMES = {"tas": "تاس", "bowling": "بولینگ", "basketball": "بسکتبال", "dart": "دارت"}
PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
CURRENCY = "داگز"

active_games = {}
user_state = {}

# ==================== PAYOUT ====================
def get_payout(bet):
    if bet <= 100:
        return int(bet * 1.8)
    elif bet <= 200:
        return int(bet * 1.3)
    elif bet <= 500:
        return int(bet * 0.96)
    elif bet <= 1000:
        return int(bet * 0.85)
    elif bet <= 2000:
        return int(bet * 0.8)
    else:
        return int(bet * 0.76)

# ==================== DATABASE ====================
DB = "gamebot.db"

def db_init():
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        balance INTEGER DEFAULT 0, referrer_id INTEGER DEFAULT 0,
        referral_count INTEGER DEFAULT 0, ref_rewarded INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        type TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
        amount INTEGER, status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

def ensure_user(uid, username=None, fname=None):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)",
                  (uid, username or "", fname or ""))
    else:
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                  (username or "", fname or "", uid))
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = c.fetchone(); conn.close(); return r

def get_balance(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    r = c.fetchone(); conn.close()
    return r[0] if r else 0

def change_balance(uid, amount, desc, ttype="game"):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    c.execute("INSERT INTO transactions (user_id, amount, type, description) VALUES (?,?,?,?)",
              (uid, amount, ttype, desc))
    conn.commit(); conn.close()

def find_by_username(uname):
    uname = uname.replace("@", "").strip().lower()
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id, username, first_name FROM users WHERE LOWER(username)=?", (uname,))
    r = c.fetchone(); conn.close(); return r

def transfer(from_id, to_id, amount):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (from_id,))
    r = c.fetchone()
    if not r or r[0] < amount:
        conn.close(); return False
    c.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, from_id))
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, to_id))
    c.execute("INSERT INTO transactions (user_id, amount, type, description) VALUES (?,?,?,?)",
              (from_id, -amount, "transfer_out", f"به {to_id}"))
    c.execute("INSERT INTO transactions (user_id, amount, type, description) VALUES (?,?,?,?)",
              (to_id, amount, "transfer_in", f"از {from_id}"))
    conn.commit(); conn.close(); return True

def add_referral(referrer_id):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?", (referrer_id,))
    conn.commit(); conn.close()

def mark_ref_rewarded(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET ref_rewarded=1 WHERE user_id=?", (uid,))
    conn.commit(); conn.close()

def get_all_users():
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC")
    r = c.fetchall(); conn.close(); return r

def create_withdrawal(uid, uname, amount):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO withdrawals (user_id, username, amount) VALUES (?,?,?)",
              (uid, uname or "", amount))
    wid = c.lastrowid; conn.commit(); conn.close(); return wid

def get_withdrawals(status="pending"):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT * FROM withdrawals WHERE status=? ORDER BY id DESC", (status,))
    r = c.fetchall(); conn.close(); return r

def update_withdrawal(wid, status):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid))
    conn.commit(); conn.close()

# ==================== HELPERS ====================
def is_owner(uid): return uid in OWNER_IDS

def calc_points(game_type, value):
    if game_type == "basketball":
        return value if value >= 4 else 0
    return value

def fmt_result(game_type, value, points):
    if game_type == "basketball":
        return f"گل +{points}" if points > 0 else "اوت"
    return f"+{points}"

def user_tag(uid, name):
    return f"<a href='tg://user?id={uid}'>{name}</a>"

async def throw_n_times(context, chat_id, game_type, n=3):
    emoji = GAME_EMOJI[game_type]
    total = 0
    details = []
    for i in range(n):
        dice = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
        val = dice.dice.value
        pts = calc_points(game_type, val)
        total += pts
        details.append((val, pts))
        await asyncio.sleep(3.2)
    return total, details

# ==================== MAIN MENU ====================
async def show_main_menu(target, user, is_edit=False):
    ensure_user(user.id, user.username, user.first_name)
    bal = get_balance(user.id)
    
    kb = [
        [InlineKeyboardButton("زیرمجموعه‌گیری", callback_data="u_ref")],
        [InlineKeyboardButton("برداشت", callback_data="u_wd")],
        [InlineKeyboardButton("موجودی", callback_data="u_bal")],
    ]
    if is_owner(user.id):
        kb.append([InlineKeyboardButton("پنل مدیریت", callback_data="a_panel")])
    
    text = (
        f"سلام {user.first_name}!\n\n"
        f"به بات DAWGS خوش اومدی!\n\n"
        f"موجودی شما: {bal} {CURRENCY}\n\n"
        f"برای بازی به گپ برو:\n{GROUP_LINK}"
    )
    
    if is_edit:
        await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ==================== START / HELP ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure_user(u.id, u.username, u.first_name)
    
    args = context.args
    user = get_user(u.id)
    referrer_id = 0
    if args and args[0].startswith("ref_"):
        try: referrer_id = int(args[0].replace("ref_", ""))
        except: pass
    
    if referrer_id and referrer_id != u.id and user and user[6] == 0:
        add_referral(referrer_id)
        change_balance(referrer_id, REFERRAL_REWARD, f"زیرمجموعه: {u.first_name}", "referral")
        mark_ref_rewarded(u.id)
        try:
            await context.bot.send_message(
                referrer_id,
                f"یک نفر با لینک تو عضو شد!\n+{REFERRAL_REWARD} {CURRENCY}"
            )
        except: pass
    
    await show_main_menu(update.message, u, is_edit=False)

async def help_cmd(update, context):
    await update.message.reply_text(
        "راهنمای کامل\n\n"
        "بازی‌ها (در گپ):\n"
        "1 تاس 100\n"
        "1 بولینگ 100\n"
        "1 بسکتبال 100\n"
        "1 دارت 100\n\n"
        "زوج/فرد:\n"
        "100 زوج\n"
        "100 فرد\n\n"
        "موجودی:\n"
        "م یا موجودی\n\n"
        "انتقال:\n"
        "انتقال 500 + ریپلای\n"
        "انتقال 500 @username\n\n"
        f"حداقل بازی: {MIN_BET} {CURRENCY}\n"
        f"حداقل برداشت: {MIN_WITHDRAW} {CURRENCY}"
    )

# ==================== USER MENU ====================
async def cb_user_ref(update, context):
    q = update.callback_query; await q.answer()
    u = q.from_user
    ensure_user(u.id, u.username, u.first_name)
    bot_user = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_user}?start=ref_{u.id}"
    user = get_user(u.id)
    cnt = user[5] if user else 0
    
    await q.edit_message_text(
        f"زیرمجموعه‌گیری\n\n"
        f"لینک دعوت تو:\n{link}\n\n"
        f"تعداد زیرمجموعه: {cnt}\n"
        f"پاداش هر نفر: {REFERRAL_REWARD} {CURRENCY}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_menu")]])
    )

async def cb_user_bal(update, context):
    q = update.callback_query; await q.answer()
    bal = get_balance(q.from_user.id)
    await q.edit_message_text(
        f"موجودی شما: {bal} {CURRENCY}\n\n"
        f"برای بازی به گپ برو:\n{GROUP_LINK}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_menu")]])
    )

async def cb_user_wd(update, context):
    q = update.callback_query; await q.answer()
    bal = get_balance(q.from_user.id)
    if bal < MIN_WITHDRAW:
        await q.edit_message_text(
            f"حداقل برداشت: {MIN_WITHDRAW} {CURRENCY}\n"
            f"موجودی تو: {bal} {CURRENCY}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_menu")]])
        )
        return
    user_state[q.from_user.id] = "withdraw"
    await q.edit_message_text(
        f"برداشت\n\n"
        f"موجودی: {bal} {CURRENCY}\n"
        f"حداقل برداشت: {MIN_WITHDRAW} {CURRENCY}\n\n"
        f"مبلغ مورد نظر رو بفرست:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_menu")]])
    )

async def cb_back_menu(update, context):
    q = update.callback_query; await q.answer()
    user_state.pop(q.from_user.id, None)
    await show_main_menu(q, q.from_user, is_edit=True)

# ==================== GAME CANCEL ====================
async def cb_cancel_all(update, context):
    q = update.callback_query; await q.answer("لغو شد")
    try:
        await q.message.delete()
    except:
        await q.edit_message_text("لغو شد.")

# ==================== PLAY VS BOT ====================
async def cb_play_bot(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    game_type = parts[1]; bet = int(parts[2])
    uid = q.from_user.id; chat_id = q.message.chat_id
    name = q.from_user.first_name
    
    bal = get_balance(uid)
    if bal < bet:
        await q.answer("موجودی کافی نداری!", show_alert=True); return
    
    change_balance(uid, -bet, f"شرط {GAME_NAMES[game_type]}", "bet")
    
    gid = f"{chat_id}_{uid}"
    active_games[gid] = {
        "type": game_type, "bet": bet, "mode": "bot",
        "p1_id": uid, "p2_id": None,
        "p1_score": 0, "p2_score": 0,
        "state": "p1", "chat_id": chat_id,
    }
    
    emoji = GAME_EMOJI[game_type]
    kb = [[InlineKeyboardButton(f"پرتاب 3 {emoji}", callback_data=f"th_{chat_id}_{uid}")],
          [InlineKeyboardButton("لغو بازی", callback_data=f"cg_{chat_id}_{uid}")]]
    
    await q.edit_message_text(
        f"بازی {GAME_NAMES[game_type]} با ربات\n\n"
        f"شرط: {bet} {CURRENCY}\n"
        f"تعداد پرتاب: 3\n\n"
        f"امتیاز تو: 0\n"
        f"امتیاز ربات: 0\n\n"
        f"{user_tag(uid, name)} نوبت توئه، بریز!",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )

# ==================== PLAY VS USER ====================
async def cb_play_user(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    game_type = parts[1]; bet = int(parts[2])
    uid = q.from_user.id; chat_id = q.message.chat_id
    name = q.from_user.first_name
    
    bal = get_balance(uid)
    if bal < bet:
        await q.answer("موجودی کافی نداری!", show_alert=True); return
    
    gid = f"{chat_id}_{uid}"
    active_games[gid] = {
        "type": game_type, "bet": bet, "mode": "waiting",
        "p1_id": uid, "p2_id": None,
        "p1_score": 0, "p2_score": 0,
        "state": "waiting", "chat_id": chat_id,
    }
    
    kb = [[InlineKeyboardButton("شرکت می‌کنم", callback_data=f"jn_{chat_id}_{uid}")],
          [InlineKeyboardButton("لغو", callback_data=f"cg_{chat_id}_{uid}")]]
    
    await q.edit_message_text(
        f"بازی {GAME_NAMES[game_type]}\n\n"
        f"شرط: {bet} {CURRENCY}\n"
        f"تعداد پرتاب: 3 هر نفر\n\n"
        f"{user_tag(uid, name)} بازی ساخت.\n"
        f"منتظر حریف...",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )

async def cb_join(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    chat_id = int(parts[1]); p1_id = int(parts[2])
    p2_id = q.from_user.id
    p2_name = q.from_user.first_name
    gid = f"{chat_id}_{p1_id}"
    
    game = active_games.get(gid)
    if not game:
        await q.answer("بازی منقضی شده!", show_alert=True); return
    if p2_id == p1_id:
        await q.answer("خودت نمی‌تونی حریف خودت باشی!", show_alert=True); return
    if game["p2_id"] is not None:
        await q.answer("یکی دیگه حریف شد!", show_alert=True); return
    
    bet = game["bet"]
    bal = get_balance(p2_id)
    if bal < bet:
        await q.answer(f"موجودی کافی نداری! ({bal} {CURRENCY})", show_alert=True); return
    
    change_balance(p1_id, -bet, f"شرط {GAME_NAMES[game['type']]}", "bet")
    change_balance(p2_id, -bet, f"شرط {GAME_NAMES[game['type']]}", "bet")
    
    game["p2_id"] = p2_id
    game["state"] = "p1"
    
    emoji = GAME_EMOJI[game["type"]]
    kb = [[InlineKeyboardButton(f"پرتاب 3 {emoji}", callback_data=f"th_{chat_id}_{p1_id}")],
          [InlineKeyboardButton("لغو", callback_data=f"cg_{chat_id}_{p1_id}")]]
    
    await q.edit_message_text(
        f"بازی {GAME_NAMES[game['type']]}\n\n"
        f"شرط: {bet} {CURRENCY}\n"
        f"هر نفر 3 پرتاب\n\n"
        f"{user_tag(p1_id, 'بازیکن اول')}: 0\n"
        f"{user_tag(p2_id, p2_name)}: 0\n\n"
        f"{user_tag(p1_id, 'بازیکن اول')} نوبت توئه، بریز!",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )

# ==================== THROW ====================
async def cb_throw(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    chat_id = int(parts[1]); p1_id = int(parts[2])
    gid = f"{chat_id}_{p1_id}"
    game = active_games.get(gid)
    
    if not game:
        await q.edit_message_text("بازی منقضی شده!"); return
    
    thrower_id = q.from_user.id
    thrower_name = q.from_user.first_name
    game_type = game["type"]
    emoji = GAME_EMOJI[game_type]
    
    if game["state"] == "p1":
        if thrower_id != game["p1_id"]:
            await q.answer("نوبت تو نیست!", show_alert=True); return
        thrower_key = "p1"
    elif game["state"] == "p2":
        if thrower_id != game["p2_id"]:
            await q.answer("نوبت تو نیست!", show_alert=True); return
        thrower_key = "p2"
    else:
        await q.answer("نمیشه الان پرتاب کرد!", show_alert=True); return
    
    await q.edit_message_text(
        f"{user_tag(thrower_id, thrower_name)} در حال پرتاب 3 {emoji}...",
        parse_mode="HTML"
    )
    
    total, details = await throw_n_times(context, chat_id, game_type, MAX_THROWS)
    game[f"{thrower_key}_score"] = total
    
    details_text = "\n".join(
        [f"  پرتاب {i+1}: {v} → {fmt_result(game_type, v, p)}"
         for i, (v, p) in enumerate(details)]
    )
    
    if game["mode"] == "bot":
        game["state"] = "bot"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"نتیجه پرتاب‌های {user_tag(thrower_id, thrower_name)}\n\n"
                f"{details_text}\n\n"
                f"امتیاز کل تو: {total}\n\n"
                f"الان نوبت رباته..."
            ),
            parse_mode="HTML"
        )
        
        await asyncio.sleep(2)
        await context.bot.send_message(chat_id=chat_id, text="ربات داره پرتاب می‌کنه...")
        
        bot_total, bot_details = await throw_n_times(context, chat_id, game_type, MAX_THROWS)
        game["p2_score"] = bot_total
        
        bot_details_text = "\n".join(
            [f"  پرتاب {i+1}: {v} → {fmt_result(game_type, v, p)}"
             for i, (v, p) in enumerate(bot_details)]
        )
        
        await finish_bot_game(context, chat_id, game, bot_details_text, bot_total)
    
    else:
        if thrower_key == "p1":
            game["state"] = "p2"
            kb = [[InlineKeyboardButton(f"پرتاب 3 {emoji}", callback_data=f"th_{chat_id}_{p1_id}")],
                  [InlineKeyboardButton("لغو", callback_data=f"cg_{chat_id}_{p1_id}")]]
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"نتیجه پرتاب‌های {user_tag(thrower_id, thrower_name)}\n\n"
                    f"{details_text}\n\n"
                    f"امتیاز: {total}\n\n"
                    f"{user_tag(game['p2_id'], 'بازیکن دوم')} نوبت توئه، بریز!"
                ),
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML"
            )
        else:
            await finish_user_game(context, chat_id, game, details_text, total)

# ==================== FINISH ====================
async def finish_bot_game(context, chat_id, game, details_text, bot_score):
    game_type = game["type"]; bet = game["bet"]
    p1 = game["p1_score"]; p2 = bot_score
    uid = game["p1_id"]; payout = get_payout(bet)
    
    if p1 > p2:
        result = "تو بردی!"
        reward_text = f"جایزه: +{payout} {CURRENCY}"
        change_balance(uid, payout, f"برد در {GAME_NAMES[game_type]}", "win")
    elif p1 < p2:
        result = "تو باختی!"
        reward_text = f"باخت: -{bet} {CURRENCY}"
    else:
        result = "مساوی!"
        reward_text = f"برگشتی: +{bet} {CURRENCY}"
        change_balance(uid, bet, f"مساوی در {GAME_NAMES[game_type]}", "draw")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"نتیجه نهایی {GAME_NAMES[game_type]}\n\n"
            f"پرتاب‌های ربات:\n{details_text}\n\n"
            f"امتیاز تو: {p1}\n"
            f"امتیاز ربات: {p2}\n\n"
            f"{result}\n{reward_text}"
        )
    )
    
    active_games.pop(f"{chat_id}_{uid}", None)

async def finish_user_game(context, chat_id, game, details_text, p2_score):
    game_type = game["type"]; bet = game["bet"]
    p1 = game["p1_score"]; p2 = p2_score
    p1_id = game["p1_id"]; p2_id = game["p2_id"]
    payout = get_payout(bet)
    
    if p1 > p2:
        result = f"{user_tag(p1_id, 'بازیکن اول')} برنده شد!"
        reward_text = f"جایزه: +{payout} {CURRENCY}"
        change_balance(p1_id, payout, f"برد در {GAME_NAMES[game_type]}", "win")
    elif p2 > p1:
        result = f"{user_tag(p2_id, 'بازیکن دوم')} برنده شد!"
        reward_text = f"جایزه: +{payout} {CURRENCY}"
        change_balance(p2_id, payout, f"برد در {GAME_NAMES[game_type]}", "win")
    else:
        result = "مساوی! پول برگشت."
        reward_text = f"هر کدوم +{bet} {CURRENCY}"
        change_balance(p1_id, bet, f"مساوی در {GAME_NAMES[game_type]}", "draw")
        change_balance(p2_id, bet, f"مساوی در {GAME_NAMES[game_type]}", "draw")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"نتیجه نهایی {GAME_NAMES[game_type]}\n\n"
            f"بازیکن اول: {p1}\n"
            f"بازیکن دوم: {p2}\n\n"
            f"{result}\n{reward_text}"
        ),
        parse_mode="HTML"
    )
    
    active_games.pop(f"{chat_id}_{p1_id}", None)

# ==================== CANCEL GAME ====================
async def cb_cancel_game(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    chat_id = int(parts[1]); p1_id = int(parts[2])
    gid = f"{chat_id}_{p1_id}"
    game = active_games.get(gid)
    
    if not game:
        await q.edit_message_text("بازی منقضی شده."); return
    
    if q.from_user.id not in [game["p1_id"], game.get("p2_id")]:
        await q.answer("اجازه نداری!", show_alert=True); return
    
    bet = game["bet"]
    change_balance(game["p1_id"], bet, "لغو بازی", "refund")
    if game.get("p2_id"):
        change_balance(game["p2_id"], bet, "لغو بازی", "refund")
    
    await q.edit_message_text("بازی لغو شد و پول برگشت.")
    active_games.pop(gid, None)

# ==================== ZOJ/FARD ====================
async def play_even_odd(context, chat_id, user, bet, choice):
    change_balance(user.id, -bet, f"شرط {choice}", "bet")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"بازی زوج/فرد\n\nانتخاب: {choice}\nمبلغ: {bet} {CURRENCY}\n\nدر حال پرتاب..."
    )
    
    dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
    value = dice_msg.dice.value
    
    await asyncio.sleep(3)
    
    is_even = value % 2 == 0
    user_won = (choice == "زوج" and is_even) or (choice == "فرد" and not is_even)
    
    payout = get_payout(bet)
    
    if user_won:
        change_balance(user.id, payout, f"برد در {choice}", "win")
        result = "بردی!"
        reward = f"جایزه: +{payout} {CURRENCY}"
    else:
        result = "باختی!"
        reward = f"باخت: -{bet} {CURRENCY}"
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"نتیجه بازی زوج/فرد\n\n"
            f"انتخاب تو: {choice}\n"
            f"عدد اومده: {value} ({'زوج' if is_even else 'فرد'})\n\n"
            f"{result}\n{reward}"
        )
    )

# ==================== MESSAGE HANDLER ====================
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    text = msg.text.strip()
    user = update.effective_user
    chat = update.effective_chat
    
    # ========== پیوی ==========
    if chat.type == "private":
        ensure_user(user.id, user.username, user.first_name)
        
        if user_state.get(user.id) == "withdraw":
            try:
                amount = int(text.translate(PERSIAN))
            except:
                await msg.reply_text("یه عدد بفرست."); return
            
            bal = get_balance(user.id)
            if amount < MIN_WITHDRAW:
                await msg.reply_text(f"حداقل {MIN_WITHDRAW} {CURRENCY}"); return
            if amount > bal:
                await msg.reply_text(f"موجودی کافی نداری! ({bal} {CURRENCY})"); return
            
            change_balance(user.id, -amount, "درخواست برداشت", "withdraw")
            wid = create_withdrawal(user.id, user.username, amount)
            user_state.pop(user.id, None)
            
            try:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=(
                        f"درخواست برداشت جدید\n\n"
                        f"#{wid}\n"
                        f"کاربر: @{user.username or user.first_name}\n"
                        f"آیدی: {user.id}\n"
                        f"مبلغ: {amount} {CURRENCY}"
                    )
                )
            except Exception as e:
                logging.error(f"channel error: {e}")
            
            await msg.reply_text(
                f"درخواست برداشت {amount} {CURRENCY} ثبت شد.\nمنتظر تایید ادمین باش."
            )
            return
        
        if is_owner(user.id) and user_state.get(user.id, "").startswith("admin_"):
            await handle_admin_input(update, context); return
        
        return
    
    # ========== گپ ==========
    if chat.id != ALLOWED_GROUP_ID:
        return
    
    ensure_user(user.id, user.username, user.first_name)
    
    # موجودی
    if text in ("موجودی", "م"):
        bal = get_balance(user.id)
        await msg.reply_text(f"موجودی {user.first_name}: {bal} {CURRENCY}")
        return
    
    # انتقال / واریز
    if text.startswith("انتقال") or text.startswith("واریز"):
        parts = text.split()
        
        if msg.reply_to_message:
            if len(parts) < 2:
                await msg.reply_text("فرمت: انتقال 500 (با ریپلای)"); return
            try:
                amount = int(parts[1].translate(PERSIAN))
            except:
                await msg.reply_text("عدد نامعتبر."); return
            
            target = msg.reply_to_message.from_user
            if target.id == user.id:
                await msg.reply_text("به خودت نمی‌تونی!"); return
            if target.is_bot:
                await msg.reply_text("به بات نمی‌تونی!"); return
            
            ensure_user(target.id, target.username, target.first_name)
            bal = get_balance(user.id)
            if bal < amount:
                await msg.reply_text(f"موجودی کافی نداری! ({bal} {CURRENCY})"); return
            
            if transfer(user.id, target.id, amount):
                await msg.reply_text(f"{amount} {CURRENCY} به {target.first_name} منتقل شد.")
                try:
                    await context.bot.send_message(
                        target.id,
                        f"{amount} {CURRENCY} از {user.first_name} دریافت کردی!"
                    )
                except: pass
            return
        
        if len(parts) >= 3:
            try:
                amount = int(parts[1].translate(PERSIAN))
            except:
                await msg.reply_text("فرمت: انتقال 500 @username"); return
            
            target_uname = parts[2]
            target = find_by_username(target_uname)
            if not target:
                await msg.reply_text(f"کاربر {target_uname} پیدا نشد!"); return
            
            target_id, _, target_name = target
            if target_id == user.id:
                await msg.reply_text("به خودت نمی‌تونی!"); return
            
            bal = get_balance(user.id)
            if bal < amount:
                await msg.reply_text(f"موجودی کافی نداری! ({bal} {CURRENCY})"); return
            
            if transfer(user.id, target_id, amount):
                await msg.reply_text(f"{amount} {CURRENCY} به {target_uname} منتقل شد.")
                try:
                    await context.bot.send_message(
                        target_id,
                        f"{amount} {CURRENCY} از {user.first_name} دریافت کردی!"
                    )
                except: pass
            return
        else:
            await msg.reply_text("فرمت:\nانتقال 500 + ریپلای\nیا انتقال 500 @username")
            return
    
    parts = text.split()
    
    # زوج/فرد
    if len(parts) == 2:
        parts_clean = [p.translate(PERSIAN) for p in parts]
        if parts[1] in ("زوج", "فرد"):
            try:
                bet = int(parts_clean[0])
            except:
                await msg.reply_text("فرمت: 100 زوج یا 100 فرد"); return
            
            if bet < MIN_BET:
                await msg.reply_text(f"حداقل بازی {MIN_BET} {CURRENCY}"); return
            
            bal = get_balance(user.id)
            if bal < bet:
                await msg.reply_text(f"موجودی کافی نداری! ({bal} {CURRENCY})"); return
            
            await play_even_odd(context, chat.id, user, bet, parts[1])
            return
    
    # بازی‌ها
    if len(parts) >= 3:
        game_map = {"تاس": "tas", "بولینگ": "bowling",
                    "بسکتبال": "basketball", "دارت": "dart"}
        parts_clean = [p.translate(PERSIAN) for p in parts]
        
        if parts[1] in game_map:
            try:
                bet = int(parts_clean[2])
            except:
                await msg.reply_text("فرمت: 1 تاس 100"); return
            
            if bet < MIN_BET:
                await msg.reply_text(f"حداقل بازی {MIN_BET} {CURRENCY}"); return
            
            bal = get_balance(user.id)
            if bal < bet:
                await msg.reply_text(f"موجودی کافی نداری! ({bal} {CURRENCY})"); return
            
            game_type = game_map[parts[1]]
            kb = [
                [InlineKeyboardButton("بازی با ربات", callback_data=f"vb_{game_type}_{bet}")],
                [InlineKeyboardButton("بازی با دوست", callback_data=f"vu_{game_type}_{bet}")],
                [InlineKeyboardButton("لغو", callback_data="cancel_all")],
            ]
            await msg.reply_text(
                f"بازی {GAME_NAMES[game_type]} | شرط: {bet} {CURRENCY}\n\n"
                f"چطور بازی کنی؟",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

# ==================== ADMIN PANEL ====================
def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("شارژ موجودی", callback_data="a_chg")],
        [InlineKeyboardButton("کسر موجودی", callback_data="a_ded")],
        [InlineKeyboardButton("موجودی کاربران", callback_data="a_usr")],
        [InlineKeyboardButton("افزایش زیرمجموعه", callback_data="a_ref")],
        [InlineKeyboardButton("درخواست‌های برداشت", callback_data="a_wd")],
        [InlineKeyboardButton("بازگشت", callback_data="back_menu")],
    ])

async def admin_cmd(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("دسترسی نداری!"); return
    await update.message.reply_text("پنل مدیریت", reply_markup=admin_kb())

async def cb_admin(update, context):
    q = update.callback_query; await q.answer()
    if not is_owner(q.from_user.id):
        await q.answer("!", show_alert=True); return
    
    if q.data == "a_panel":
        await q.edit_message_text("پنل مدیریت", reply_markup=admin_kb())
    elif q.data == "a_chg":
        user_state[q.from_user.id] = "admin_charge"
        await q.edit_message_text(
            "شارژ موجودی\n\nفرمت: user_id amount\nیا: @username amount\n\nمثال: 123456789 500\nمثال: @MMAD_Tek 500",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="a_panel")]])
        )
    elif q.data == "a_ded":
        user_state[q.from_user.id] = "admin_deduct"
        await q.edit_message_text(
            "کسر موجودی\n\nفرمت: user_id amount\nمثال: 123456789 500",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="a_panel")]])
        )
    elif q.data == "a_ref":
        user_state[q.from_user.id] = "admin_referral"
        await q.edit_message_text(
            "افزایش زیرمجموعه\n\nفرمت: user_id count\nمثال: 123456789 5",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="a_panel")]])
        )
    elif q.data == "a_usr":
        users = get_all_users()
        txt = "موجودی کاربران\n\n"
        for i, (uid, uname, bal) in enumerate(users[:50], 1):
            name = f"@{uname}" if uname else str(uid)
            txt += f"{i}_{name} - {bal} {CURRENCY}\n"
        txt += f"\nکل: {len(users)}"
        await q.edit_message_text(txt,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="a_panel")]]))
    elif q.data == "a_wd":
        wds = get_withdrawals("pending")
        if not wds:
            await q.edit_message_text("هیچ درخواستی نیست.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="a_panel")]]))
            return
        txt = "درخواست‌های برداشت\n\n"
        kb_rows = []
        for w in wds[:10]:
            wid, uid, uname, amount, status, created = w
            name = f"@{uname}" if uname else str(uid)
            txt += f"#{wid} {name} - {amount} {CURRENCY}\n"
            if status == "pending":
                kb_rows.append([
                    InlineKeyboardButton(f"تایید {wid}", callback_data=f"wd_ok_{wid}"),
                    InlineKeyboardButton(f"رد {wid}", callback_data=f"wd_no_{wid}")
                ])
        kb_rows.append([InlineKeyboardButton("بازگشت", callback_data="a_panel")])
        await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb_rows))

async def cb_withdraw_action(update, context):
    q = update.callback_query; await q.answer()
    if not is_owner(q.from_user.id):
        await q.answer("!", show_alert=True); return
    
    parts = q.data.split("_")
    action = parts[1]; wid = int(parts[2])
    
    if action == "ok":
        update_withdrawal(wid, "approved")
        await q.edit_message_text(f"برداشت #{wid} تایید شد.")
    else:
        update_withdrawal(wid, "rejected")
        await q.edit_message_text(f"برداشت #{wid} رد شد.")

async def handle_admin_input(update, context):
    uid = update.effective_user.id
    state = user_state.get(uid, "")
    text = update.message.text.strip()
    
    try:
        text_clean = text.translate(PERSIAN)
        parts = text_clean.split()
        
        if len(parts) < 2:
            await update.message.reply_text("فرمت: user_id amount"); return
        
        target_input = parts[0]
        amount = int(parts[1])
        
        if target_input.startswith("@"):
            target = find_by_username(target_input)
            if not target:
                await update.message.reply_text(f"کاربر {target_input} پیدا نشد!"); return
            target_id = target[0]
        else:
            target_id = int(target_input)
        
        ensure_user(target_id)
        bal_before = get_balance(target_id)
        
        if state == "admin_charge":
            change_balance(target_id, amount, "شارژ ادمین", "admin_charge")
            bal_after = get_balance(target_id)
            await update.message.reply_text(
                f"شارژ موفق\n\nکاربر: {target_id}\nقبل: {bal_before} {CURRENCY}\nاضافه شد: {amount} {CURRENCY}\nبعد: {bal_after} {CURRENCY}"
            )
        elif state == "admin_deduct":
            change_balance(target_id, -amount, "کسر ادمین", "admin_deduct")
            bal_after = get_balance(target_id)
            await update.message.reply_text(
                f"کسر موفق\n\nکاربر: {target_id}\nقبل: {bal_before} {CURRENCY}\nکم شد: {amount} {CURRENCY}\nبعد: {bal_after} {CURRENCY}"
            )
        elif state == "admin_referral":
            conn = sqlite3.connect(DB); c = conn.cursor()
            c.execute("UPDATE users SET referral_count = referral_count + ? WHERE user_id=?",
                      (amount, target_id))
            conn.commit(); conn.close()
            await update.message.reply_text(f"{amount} زیرمجموعه به {target_id} اضافه شد.")
        
        user_state.pop(uid, None)
    except ValueError:
        await update.message.reply_text("خطا در اعداد!\nمثال: 123456789 500")
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")

# ==================== MAIN ====================
def main():
    logging.basicConfig(level=logging.INFO)
    db_init()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    
    app.add_handler(CallbackQueryHandler(cb_back_menu, pattern="^back_menu$"))
    app.add_handler(CallbackQueryHandler(cb_user_ref, pattern="^u_ref$"))
    app.add_handler(CallbackQueryHandler(cb_user_bal, pattern="^u_bal$"))
    app.add_handler(CallbackQueryHandler(cb_user_wd, pattern="^u_wd$"))
    
    app.add_handler(CallbackQueryHandler(cb_cancel_all, pattern="^cancel_all$"))
    app.add_handler(CallbackQueryHandler(cb_play_bot, pattern="^vb_"))
    app.add_handler(CallbackQueryHandler(cb_play_user, pattern="^vu_"))
    app.add_handler(CallbackQueryHandler(cb_join, pattern="^jn_"))
    app.add_handler(CallbackQueryHandler(cb_throw, pattern="^th_"))
    app.add_handler(CallbackQueryHandler(cb_cancel_game, pattern="^cg_"))
    
    app.add_handler(CallbackQueryHandler(cb_admin, pattern="^a_"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_action, pattern="^wd_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    print("DAWGS bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
